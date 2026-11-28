import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import * as z from 'zod';
import {
  ensureMachine,
  ensurePort,
  mintAccessKey,
  run,
  waitRunning,
} from './machine.ts';

const SERVER_PORT = 8787;
const AUTH_PORT = 8788;
const SETUP_TIMEOUT_MS = 1_800_000;
const UPLOAD_TIMEOUT_MS = 120_000;
const CHUNK_BYTES = 256 * 1024;
const ARCHIVE_MAX_BYTES = 64 * 1024 * 1024;

const Action = z.enum(['deploy', 'retire', 'rollback']).default('deploy');
const DeployEnv = z.object({
  DOGGYBANK_SITE_URL: z.url(),
  DOGGYBANK_MACHINE_ID: z.string().optional(),
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

const action = Action.parse(process.argv[2]);
const setup = readFileSync(new URL('./setup.sh', import.meta.url), 'utf8');

if (action === 'retire' || action === 'rollback') {
  const {DOGGYBANK_MACHINE_ID: machineId} = SwitchEnv.parse(process.env);
  await waitRunning(machineId);
  const stdout = await checkedRun(
    machineId,
    ['bash', '-s', '--', action],
    setup,
    SETUP_TIMEOUT_MS,
  );
  console.log(stdout);
} else {
  const commit = cleanCommit();
  const env = DeployEnv.parse(process.env);

  const machineId = await ensureMachine(env.DOGGYBANK_MACHINE_ID);
  console.log(`Machine ${machineId}`);
  await waitRunning(machineId);

  const port = await ensurePort(machineId, SERVER_PORT);
  const authPort = await ensurePort(machineId, AUTH_PORT);
  // Keys print only on a Machine's first deploy, for the Worker's PORT_KEY and
  // AUTH_PORT_KEY secrets. Later deploys reuse the ports and mint nothing.
  if (env.DOGGYBANK_MACHINE_ID === undefined) {
    console.log(`Port key: ${await mintAccessKey(machineId, port)}`);
    console.log(`Auth port key: ${await mintAccessKey(machineId, authPort)}`);
  }
  const hosts = [
    ...new Set(
      [port.application_url, port.url]
        .filter(url => url !== undefined)
        .map(url => new URL(url).hostname),
    ),
  ];

  const archivePath = await uploadArchive(machineId, commit);
  const stdout = await checkedRun(
    machineId,
    [
      'env',
      `SITE_URL=${env.DOGGYBANK_SITE_URL}`,
      'bash',
      '-s',
      '--',
      'deploy',
      commit,
      archivePath,
      ...hosts,
    ],
    setup,
    SETUP_TIMEOUT_MS,
  );
  console.log(stdout);
  console.log(`Share URL: ${port.url ?? port.application_url}`);
  console.log(`API URL:   ${port.application_url}`);
  console.log(`Auth URL:  ${authPort.application_url}`);
  console.log(
    `Check:     curl -fsS -H "X-Dedalus-Port-Key: <port key>" ${port.application_url}`,
  );
}
