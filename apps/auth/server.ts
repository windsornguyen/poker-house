import {createServer} from 'node:http';

import {toNodeHandler} from 'better-auth/node';

import {auth} from './auth.ts';

const PORT = 8788;

createServer(toNodeHandler(auth)).listen(PORT, '0.0.0.0', () => {
  console.log(`Poker House auth on port ${String(PORT)}`);
});
