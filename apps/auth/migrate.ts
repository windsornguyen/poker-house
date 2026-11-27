import {getMigrations} from 'better-auth/db/migration';

import {options} from './auth.ts';

const {runMigrations} = await getMigrations(options);
await runMigrations();
await options.database.end();
console.log('Auth tables are current.');
