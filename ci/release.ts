import {
  command,
  eq,
  format,
  github,
  job,
  secret,
  unsafeShell,
  workflow,
  type GitHubRunStep,
  type GitHubWorkflowStep,
  type WorkflowCommand,
} from '@dedalus-labs/hollywood';

const ubuntu = 'ubuntu-24.04';
const site = 'https://doggybank.io';
const checkoutV4 = 'actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5';
const pnpmSetupV4 =
  'pnpm/action-setup@b906affcce14559ad1aafd4ab0e942779e9f58b1';
const setupNodeV4 =
  'actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020';
const setupUvV10 =
  'astral-sh/setup-uv@1db35dd8eee11c5894872e0b383ae6c406cf738d';

function run(file: string, ...args: readonly string[]): WorkflowCommand {
  return command({file, args});
}

function pnpm(...args: readonly string[]): WorkflowCommand {
  return run('pnpm', ...args);
}

function web(...args: readonly string[]): WorkflowCommand {
  return pnpm('--filter', '@doggybank/web', ...args);
}

function setup(): readonly GitHubWorkflowStep[] {
  return [
    {uses: checkoutV4, with: {'persist-credentials': false}},
    {uses: pnpmSetupV4},
    {
      uses: setupNodeV4,
      with: {'node-version-file': '.node-version', cache: 'pnpm'},
    },
    {uses: setupUvV10},
    {run: pnpm('install', '--frozen-lockfile')},
    {
      run: run(
        'uv',
        'sync',
        '--frozen',
        '--all-packages',
        '--group',
        'check',
        '--group',
        'test',
      ),
    },
  ];
}

// The server's tests start a throwaway Postgres 19, the version production runs.
function postgres(): readonly GitHubRunStep[] {
  return [
    {
      run: run(
        'sudo',
        '/usr/share/postgresql-common/pgdg/apt.postgresql.org.sh',
        '-y',
      ),
    },
    {run: run('sudo', 'apt-get', 'install', '-y', '-qq', 'postgresql-19')},
    {run: unsafeShell('echo /usr/lib/postgresql/19/bin >> "$GITHUB_PATH"')},
  ];
}

const cloudflare = {
  CLOUDFLARE_API_TOKEN: secret('CLOUDFLARE_API_TOKEN'),
  CLOUDFLARE_ACCOUNT_ID: secret('CLOUDFLARE_ACCOUNT_ID'),
};

/** Verifies every push and pull request, and deploys main: the Machine, the site, the docs. */
export const release = workflow({
  name: 'Release',
  on: {push: {branches: ['main']}, pull_request: {}},
  // Deploys run one at a time and in order, never interleaved.
  concurrency: {
    group: format('{0}-{1}', github.workflow, github.ref),
    'cancel-in-progress': false,
  },
  permissions: {contents: 'read'},
  jobs: {
    verify: job({
      name: 'Verify',
      'runs-on': ubuntu,
      steps: [...setup(), ...postgres(), {name: 'Check', run: pnpm('check')}],
    }),
    deploy: job({
      name: 'Deploy',
      'runs-on': ubuntu,
      needs: ['verify'],
      if: eq(github.ref, 'refs/heads/main'),
      environment: {name: 'Production', url: site},
      steps: [
        ...setup(),
        // The server goes first: the page ignores fields it does not know, so a newer
        // server never breaks an older page.
        {
          name: 'Deploy the Machine',
          env: {
            DEDALUS_API_KEY: secret('DEDALUS_API_KEY'),
            DOGGYBANK_MACHINE_ID: secret('DOGGYBANK_MACHINE_ID'),
            DOGGYBANK_SITE_URL: site,
          },
          run: run('node', 'apps/server/deploy/provision.ts'),
        },
        {name: 'Build the site', run: web('build')},
        {
          name: 'Deploy the site',
          env: cloudflare,
          run: web('exec', 'wrangler', 'deploy'),
        },
        {name: 'Build the docs', run: pnpm('docs:build')},
        {
          name: 'Deploy the docs',
          env: cloudflare,
          run: web(
            'exec',
            'wrangler',
            'deploy',
            '--config',
            '../../docs/wrangler.jsonc',
          ),
        },
        {
          name: 'Smoke the page',
          run: run('curl', '-fsS', '-o', '/dev/null', `${site}/`),
        },
        {
          name: 'Smoke the site',
          run: run(
            'curl',
            '-fsS',
            '-o',
            '/dev/null',
            `${site}/api/auth/get-session`,
          ),
        },
        {
          name: 'Smoke the docs',
          run: run(
            'curl',
            '-fsS',
            '-o',
            '/dev/null',
            'https://docs.doggybank.io/',
          ),
        },
        {
          name: 'Play two hands',
          env: {DOGGYBANK_BOT_ACCOUNTS: secret('DOGGYBANK_BOT_ACCOUNTS')},
          run: unsafeShell(
            'printf %s "$DOGGYBANK_BOT_ACCOUNTS" > "$RUNNER_TEMP/accounts.json" && ' +
              'DOGGYBANK_ACCOUNTS="$RUNNER_TEMP/accounts.json" uv run --package doggybank-players ' +
              `python -m doggybank_players.match --site ${site} --room-hands 2 --log "$RUNNER_TEMP/hands.jsonl"`,
          ),
        },
      ],
    }),
  },
});
