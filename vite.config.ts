import {defineConfig, type UserConfig} from 'vite-plus';

type LintOverride = NonNullable<
  NonNullable<UserConfig['lint']>['overrides']
>[number];

const WEB_SOURCES = '*.{ts,tsx}';
const MAX_DEPTH = 8;
const NUMBER_PARSING =
  'Use Number() to parse numbers; parseInt only with a radix other than 10.';

// The web client is self-contained: no import leaves apps/web or names an absolute path. A glob
// cannot resolve a path, so each directory depth gets the number of parent steps that leave it.
function staysInWeb(depth: number): LintOverride {
  return {
    files: ['apps/web/' + '*/'.repeat(depth) + WEB_SOURCES],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              regex: `^(\\.\\./){${String(depth)}}\\.\\.(/|$)`,
              message: 'Imports stay inside apps/web.',
            },
            {regex: '^/', message: 'No absolute imports.'},
          ],
        },
      ],
    },
  };
}

export default defineConfig({
  fmt: {
    printWidth: 80,
    singleQuote: true,
    bracketSpacing: false,
    trailingComma: 'all',
    arrowParens: 'avoid',
    // The Python packages and prose keep their own formatting.
    ignorePatterns: [
      'apps/server/src/**',
      'packages/**',
      '**/*.md',
      '**/*.toml',
      '**/licenses/*/LICENSE.md',
      '**/.react-router/**',
      '**/.wrangler/**',
      '**/dist/**',
      'typings/**',
    ],
  },
  lint: {
    plugins: ['typescript', 'react', 'import'],
    jsPlugins: [{name: 'vite-plus', specifier: 'vite-plus/oxlint-plugin'}],
    ignorePatterns: [
      '**/dist/**',
      '**/.react-router/**',
      '**/.wrangler/**',
      'apps/web/addons/**',
      'apps/web/piece_sets/**',
    ],
    options: {typeAware: true, typeCheck: true},
    rules: {
      'vite-plus/prefer-vite-plus-imports': 'error',
      'block-scoped-var': 'error',
      curly: ['error', 'multi-line'],
      'default-case': 'error',
      // A relative import names its file, which both Vite and Node resolve.
      'import/extensions': ['error', 'always', {ignorePackages: true}],
      eqeqeq: 'error',
      'no-var': 'error',
      'prefer-const': 'error',
      'no-restricted-globals': [
        'error',
        {name: 'parseFloat', message: NUMBER_PARSING},
      ],
      'max-lines': [
        'error',
        {max: 500, skipBlankLines: true, skipComments: true},
      ],
      'max-lines-per-function': [
        'error',
        {max: 80, skipBlankLines: true, skipComments: true},
      ],
      'react/rules-of-hooks': 'error',
      'react/exhaustive-deps': 'error',
      // An error boundary clears its error in componentDidUpdate when its reset key changes.
      'react/no-did-update-set-state': 'off',
      'typescript/array-type': [
        'error',
        {default: 'array-simple', readonly: 'array-simple'},
      ],
      'typescript/consistent-type-imports': 'error',
      'typescript/explicit-module-boundary-types': 'error',
      'typescript/no-explicit-any': 'error',
      'typescript/no-floating-promises': 'error',
      'typescript/no-non-null-assertion': 'error',
    },
    overrides: Array.from({length: MAX_DEPTH + 1}, (_, depth) =>
      staysInWeb(depth),
    ),
  },
});
