import {randomBytes} from 'node:crypto';
import process from 'node:process';

import * as z from 'zod';

import {auth, pool} from './auth.ts';

const Args = z.tuple([z.email(), z.enum(['person', 'internal', 'test'])]);
const [email, kind] = Args.parse(process.argv.slice(2));
const password = randomBytes(24).toString('base64url');

await pool.query('insert into poker.player (email, kind) values ($1, $2)', [
  email,
  kind,
]);

const context = await auth.$context;
const user = await context.internalAdapter.createUser(
  {
    email,
    name: email.split('@')[0] ?? email,
    emailVerified: true,
  },
  {method: 'admin'},
);
await context.internalAdapter.linkAccount({
  userId: user.id,
  providerId: 'credential',
  accountId: user.id,
  password: await context.password.hash(password),
});

await pool.end();
console.log(password);
