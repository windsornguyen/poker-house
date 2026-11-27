import {execFileSync} from 'node:child_process';
import {
  type IncomingMessage,
  type ServerResponse,
  createServer,
} from 'node:http';

import {toNodeHandler} from 'better-auth/node';
import * as z from 'zod';

import {auth, pool} from './auth.ts';

const PORT = 8788;
// Reached only by the Worker, which forwards nothing but /api/auth/ here.
const KEY_PATH = '/internal/api-key';
const KeyCheck = z.object({key: z.string()});
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

/** The player an agent's API key belongs to, or null for a key that is not valid. */
async function playerOfKey(request: IncomingMessage): Promise<string | null> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(chunk as Buffer);
  const {key} = KeyCheck.parse(JSON.parse(Buffer.concat(chunks).toString()));

  const checked = await auth.api.verifyApiKey({body: {key}});
  return checked.valid && checked.key ? checked.key.referenceId : null;
}

/** Answers the probes and key checks, and hands every other request to Better Auth. */
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

  if (request.url === KEY_PATH && request.method === 'POST') {
    const player = await playerOfKey(request);
    response
      .writeHead(player === null ? 401 : 200, {
        'Content-Type': 'application/json',
      })
      .end(JSON.stringify({player}));
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
