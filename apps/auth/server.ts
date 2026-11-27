import {execFileSync} from 'node:child_process';
import {
  type IncomingMessage,
  type ServerResponse,
  createServer,
} from 'node:http';

import {toNodeHandler} from 'better-auth/node';

import {auth, pool} from './auth.ts';

const PORT = 8788;
const authHandler = toNodeHandler(auth);

/** Why the database cannot answer a query, or null when it can. */
async function problem(): Promise<string | null> {
  try {
    await pool.query('select 1');
    return null;
  } catch (error) {
    return error instanceof Error ? error.message : String(error);
  }
}

/** Answers the probes, and hands every other request to Better Auth. */
async function handle(
  request: IncomingMessage,
  response: ServerResponse,
): Promise<void> {
  if (request.url === '/livez') {
    response.writeHead(200).end('live');
    return;
  }

  if (request.url === '/readyz') {
    const reason = await problem();
    response.writeHead(reason === null ? 200 : 503).end(reason ?? 'ready');
    return;
  }

  await authHandler(request, response);
}

createServer((request, response) => {
  void handle(request, response);
}).listen(PORT, '0.0.0.0', () => {
  void problem().then(reason => {
    if (reason !== null) {
      throw new Error(`The database is not ready: ${reason}`);
    }

    console.log(`Poker House auth on port ${String(PORT)}`);
    if (process.env['NOTIFY_SOCKET'] !== undefined) {
      execFileSync('systemd-notify', ['--ready']);
    }
  });
});
