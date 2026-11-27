import process from 'node:process';

import {createAuthClient} from 'better-auth/client';

import {Frame} from '../src/contract/contract.ts';
import {isEntryPoint} from './entry-point.ts';

/** Signs in to `site` and returns the session cookie its Worker checks. */
export async function signIn(
  site: string,
  email: string,
  password: string,
): Promise<string> {
  let cookie = '';
  const auth = createAuthClient({
    baseURL: site,
    fetchOptions: {
      headers: {Origin: site},
      onResponse: ({response}) => {
        cookie = response.headers
          .getSetCookie()
          .map(header => header.split(';')[0])
          .join('; ');
      },
    },
  });

  const {error} = await auth.signIn.email({email, password});
  if (error !== null) {
    throw new Error(`Signing in failed: ${error.message ?? error.statusText}`);
  }
  return cookie;
}

/** Sits in the room `code` and returns the seat's view of the table. */
export async function joinRoom(
  site: string,
  cookie: string,
  code: string,
): Promise<Frame> {
  const response = await fetch(`${site}/api/rooms/${code}/join`, {
    method: 'POST',
    headers: {cookie, 'Content-Type': 'application/json'},
    body: '{}',
  });
  if (!response.ok) {
    throw new Error(`Joining ${code} failed: ${await response.text()}`);
  }
  return Frame.parse(await response.json());
}

/** Plays `action` for the seat `frame` shows, and returns the new view. */
export async function play(
  site: string,
  cookie: string,
  frame: Frame,
  action: number,
): Promise<Frame> {
  const {id} = frame.session;
  const response = await fetch(
    `${site}/api/sessions/${id}/actions?viewer=${String(frame.viewer.seat)}`,
    {
      method: 'POST',
      headers: {cookie, 'Content-Type': 'application/json'},
      body: JSON.stringify({action, ply: null}),
    },
  );
  if (!response.ok) {
    throw new Error(
      `Playing ${String(action)} failed: ${await response.text()}`,
    );
  }
  return Frame.parse(await response.json());
}

if (isEntryPoint(import.meta.filename)) {
  const [site, code] = process.argv.slice(2);
  const email = process.env['DOGGYBANK_EMAIL'];
  const password = process.env['DOGGYBANK_PASSWORD'];
  if (!site || !code || !email || !password) {
    throw new Error(
      'Usage: DOGGYBANK_EMAIL=… DOGGYBANK_PASSWORD=… node scripts/join-room.ts SITE CODE',
    );
  }

  const cookie = await signIn(site, email, password);
  const frame = await joinRoom(site, cookie, code);
  console.log(
    `Seat ${String(frame.viewer.seat)} at ${code}, seat ${String(frame.to_move.seat)} to move.`,
  );
}
