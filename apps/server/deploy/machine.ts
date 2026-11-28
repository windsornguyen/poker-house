import {randomBytes} from 'node:crypto';

import Dedalus from 'dedalus';
import type {
  Execution,
  ExecutionOutput,
  Port,
} from 'dedalus/resources/machines/index';

const TERMINAL_STATUSES: ReadonlySet<Execution['status']> = new Set([
  'succeeded',
  'failed',
  'cancelled',
  'expired',
]);
const POLL_MS = 1000;
const RUNNING_TIMEOUT_MS = 180_000;

/** The Dedalus API, authenticated by DEDALUS_API_KEY. */
export const client = new Dedalus();

function pause(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/** Creates a Machine sized for Postgres, the game server and sign-in, and returns its ID. */
export async function createMachine(): Promise<string> {
  const machine = await client.machines.create({
    vcpu: 1,
    memory_mib: 2048,
    storage_gib: 10,
    // A sleeping Machine wakes on the next request, and a wake that fails takes the site down.
    autosleep: 'never',
  });
  return machine.machine_id;
}

/** Wakes the Machine if needed and resolves once it is running. */
export async function waitRunning(machineId: string): Promise<void> {
  const deadline = Date.now() + RUNNING_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const machine = await client.machines.retrieve({machine_id: machineId});
    if (machine.status.phase === 'running') {
      return;
    }
    if (machine.status.phase === 'failed') {
      throw new Error(
        `Machine ${machineId} failed to start: ${machine.status.last_error ?? machine.status.reason}.`,
      );
    }
    if (machine.desired_state !== 'running') {
      await client.machines.wake({machine_id: machineId});
    }
    await pause(POLL_MS);
  }
  throw new Error(
    `Machine ${machineId} did not reach running within ${RUNNING_TIMEOUT_MS / 1000} seconds.`,
  );
}

/** Runs `command` on the Machine with `stdin` and returns its result once it ends. */
export async function run(
  machineId: string,
  command: string[],
  stdin: string,
  timeoutMs: number,
): Promise<{execution: Execution; output: ExecutionOutput}> {
  const ids = {machine_id: machineId};
  let execution = await client.machines.executions.create({
    ...ids,
    command,
    stdin,
    timeout_ms: timeoutMs,
  });
  const execution_id = execution.execution_id;
  while (!TERMINAL_STATUSES.has(execution.status)) {
    await pause(execution.retry_after_ms ?? POLL_MS);
    execution = await client.machines.executions.retrieve({
      ...ids,
      execution_id,
    });
  }
  const output = await client.machines.executions.output({
    ...ids,
    execution_id,
  });
  return {execution, output};
}

/**
 * Opens `port` on the Machine and prints a minted access key for it once, labeled
 * `name`, for the Worker's secret.
 */
export async function createPort(
  machineId: string,
  port: number,
  name: string,
): Promise<Port> {
  // The API requires a sharing password for a key-protected port, which this SDK
  // version does not type yet. The Worker authenticates with a minted access key,
  // so the password is random and never kept.
  const password = randomBytes(6)
    .toString('base64url')
    .replace(/[-_]/g, '0')
    .slice(0, 8);
  const created = await client.post<Port>(`/v1/machines/${machineId}/ports`, {
    body: {port, visibility: 'key_required', password},
  });
  console.log(`${name}: ${await mintAccessKey(machineId, created)}`);
  return created;
}

/** Returns the Machine's open `port`. */
export async function findPort(machineId: string, port: number): Promise<Port> {
  for await (const open of client.machines.ports.list({
    machine_id: machineId,
  })) {
    if (open.port === port) {
      return open;
    }
  }
  throw new Error(
    `Machine ${machineId} has no port ${port}. Create the Machine with \`provision.ts create\`.`,
  );
}

// The longest lifetime the API allows, about 68 years: the Worker's keys never expire.
const ACCESS_KEY_SECONDS = 2_147_483_647;

/** Mints a key for `port` that the Worker sends as `X-Dedalus-Port-Key`. */
async function mintAccessKey(machineId: string, port: Port): Promise<string> {
  const minted = await client.machines.ports.accessKeys.mint({
    machine_id: machineId,
    port_id: port.port_id,
    expires_in: ACCESS_KEY_SECONDS,
  });
  return minted.access_key;
}
