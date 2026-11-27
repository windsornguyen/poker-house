import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import type {Port} from 'dedalus/resources/machines/index';
import * as z from 'zod';
import {ensureMachine, ensurePort, run, waitRunning} from './machine.ts';

const SERVER_PORT = 8787;
const AUTH_PORT = 8788;
const SETUP_TIMEOUT_MS = 1_800_000;

const Env = z.object({
  POKER_HOUSE_SITE_URL: z.url(),
  // The emails that may make an account, comma-separated.
  POKER_HOUSE_PLAYERS: z
    .string()
    .transform(list => list.split(','))
    .pipe(z.array(z.email()).min(1)),
  POKER_HOUSE_MACHINE_ID: z.string().optional(),
});

function announceKey(name: string, port: Port): void {
  const key = port.initial_access_key;
  if (key) {
    console.log(
      `${name}: ${key.access_key} (shown once, expires ${key.expires_at})`,
    );
  }
}

function git(...args: string[]): string {
  return execFileSync('git', args, {encoding: 'utf8'}).trim();
}

function publishedCommit(): string {
  if (git('status', '--porcelain') !== '') {
    throw new Error(
      'Commit or discard local changes first. The Machine deploys a pushed commit.',
    );
  }
  const commit = git('rev-parse', 'HEAD');
  git('fetch', '--quiet', 'origin');
  if (git('branch', '--remotes', '--contains', commit) === '') {
    throw new Error(`Push ${commit} first. The Machine clones it from origin.`);
  }
  return commit;
}

const commit = publishedCommit();
const env = Env.parse(process.env);

const machineId = await ensureMachine(env.POKER_HOUSE_MACHINE_ID);
console.log(`Machine ${machineId}`);
await waitRunning(machineId);

const port = await ensurePort(machineId, SERVER_PORT);
const authPort = await ensurePort(machineId, AUTH_PORT);
announceKey('Port key', port);
announceKey('Auth port key', authPort);
const hosts = [
  ...new Set(
    [port.application_url, port.url]
      .filter(url => url !== undefined)
      .map(url => new URL(url).hostname),
  ),
];

const setup = readFileSync(new URL('./setup.sh', import.meta.url), 'utf8');
const {execution, output} = await run(
  machineId,
  [
    'env',
    `SITE_URL=${env.POKER_HOUSE_SITE_URL}`,
    `PLAYERS=${env.POKER_HOUSE_PLAYERS.join(',')}`,
    'bash',
    '-s',
    '--',
    commit,
    ...hosts,
  ],
  setup,
  SETUP_TIMEOUT_MS,
);
if (execution.status !== 'succeeded') {
  console.error(output.stderr);
  throw new Error(
    `Setup ended ${execution.status} with exit code ${execution.exit_code}.`,
  );
}
console.log(output.stdout?.trim());
console.log(`Share URL: ${port.url ?? port.application_url}`);
console.log(`API URL:   ${port.application_url}`);
console.log(`Auth URL:  ${authPort.application_url}`);
console.log(
  `Check:     curl -fsS -H "X-Dedalus-Port-Key: <port key>" ${port.application_url}`,
);
