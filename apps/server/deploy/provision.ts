import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import * as z from 'zod';
import type {Port} from 'dedalus/resources/machines/index';
import {
  createMachine,
  createPort,
  findPort,
  run,
  waitRunning,
} from './machine.ts';

const SERVER_PORT = 8787;
const AUTH_PORT = 8788;
const SETUP_TIMEOUT_MS = 1_800_000;
const UPLOAD_TIMEOUT_MS = 120_000;
const CHUNK_BYTES = 256 * 1024;
const ARCHIVE_MAX_BYTES = 64 * 1024 * 1024;

const Action = z.enum(['create', 'deploy', 'retire', 'rollback']);
const CreateEnv = z.object({
  DOGGYBANK_MACHINE_ID: z.undefined({
    error: 'create makes a new Machine; unset DOGGYBANK_MACHINE_ID.',
  }),
});
const DeployEnv = z.object({
  DOGGYBANK_SITE_URL: z.url(),
  DOGGYBANK_MACHINE_ID: z.string().min(1),
});
const SwitchEnv = z.object({
  DOGGYBANK_MACHINE_ID: z.string().min(1),
});

function git(...args: string[]): string {
  return execFileSync('git', args, {encoding: 'utf8'}).trim();
}

function cleanCommit(): string {
  if (git('status', '--porcelain') !== '') {
    throw new Error(
      'Commit or discard local changes first. Deploys unpack a clean commit.',
    );
  }
  return git('rev-parse', 'HEAD');
}

async function checkedRun(
  machineId: string,
  command: string[],
  stdin: string,
  timeoutMs: number,
): Promise<string> {
  const {execution, output} = await run(machineId, command, stdin, timeoutMs);
  if (execution.status !== 'succeeded') {
    console.error(output.stderr);
    throw new Error(
      `Execution ended ${execution.status} with exit code ${String(execution.exit_code)}.`,
    );
  }
  return output.stdout?.trim() ?? '';
}

async function uploadArchive(
  machineId: string,
  commit: string,
): Promise<string> {
  const remotePath = `/tmp/doggybank-${commit}.tar.gz`;
  const archive = execFileSync('git', ['archive', '--format=tar.gz', commit], {
    maxBuffer: ARCHIVE_MAX_BYTES,
  });
  await checkedRun(machineId, ['rm', '-f', remotePath], '', UPLOAD_TIMEOUT_MS);
  for (let offset = 0; offset < archive.length; offset += CHUNK_BYTES) {
    const chunk = archive
      .subarray(offset, offset + CHUNK_BYTES)
      .toString('base64');
    await checkedRun(
      machineId,
      ['sh', '-c', 'base64 -d >> "$1"', 'sh', remotePath],
      chunk,
      UPLOAD_TIMEOUT_MS,
    );
  }
  return remotePath;
}

const setup = readFileSync(new URL('./setup.sh', import.meta.url), 'utf8');

/** The host names requests reach the game server by, for its allowed-host check. */
function hostsOf(port: Port): string[] {
  return [
    ...new Set(
      [port.application_url, port.url]
        .filter(url => url !== undefined)
        .map(url => new URL(url).hostname),
    ),
  ];
}

/** Makes a Machine, opens its two ports, and installs everything a deploy needs. */
async function create(): Promise<void> {
  CreateEnv.parse(process.env);
  const machineId = await createMachine();
  console.log(`Machine ${machineId}`);
  await waitRunning(machineId);

  const port = await createPort(machineId, SERVER_PORT, 'Port key');
  const authPort = await createPort(machineId, AUTH_PORT, 'Auth port key');
  console.log(
    await checkedRun(
      machineId,
      ['bash', '-s', '--', 'install'],
      setup,
      SETUP_TIMEOUT_MS,
    ),
  );
  console.log(`API URL:  ${port.application_url}`);
  console.log(`Auth URL: ${authPort.application_url}`);
}

/** Installs the clean HEAD as the idle color and moves traffic to it. */
async function deploy(): Promise<void> {
  const commit = cleanCommit();
  const env = DeployEnv.parse(process.env);
  const machineId = env.DOGGYBANK_MACHINE_ID;
  await waitRunning(machineId);

  const port = await findPort(machineId, SERVER_PORT);
  await findPort(machineId, AUTH_PORT);
  const archivePath = await uploadArchive(machineId, commit);
  const command = [
    'env',
    `SITE_URL=${env.DOGGYBANK_SITE_URL}`,
    'bash',
    '-s',
    '--',
    'deploy',
    commit,
    archivePath,
    ...hostsOf(port),
  ];
  console.log(await checkedRun(machineId, command, setup, SETUP_TIMEOUT_MS));
}

/** Runs `retire` or `rollback` on the Machine's colors. */
async function switchColors(action: 'retire' | 'rollback'): Promise<void> {
  const {DOGGYBANK_MACHINE_ID: machineId} = SwitchEnv.parse(process.env);
  await waitRunning(machineId);
  console.log(
    await checkedRun(
      machineId,
      ['bash', '-s', '--', action],
      setup,
      SETUP_TIMEOUT_MS,
    ),
  );
}

const ACTIONS: Record<z.infer<typeof Action>, () => Promise<void>> = {
  create,
  deploy,
  retire: () => switchColors('retire'),
  rollback: () => switchColors('rollback'),
};

await ACTIONS[Action.parse(process.argv[2])]();
