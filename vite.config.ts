import {defineConfig, type UserConfig} from 'vite-plus';

type LintOverride = NonNullable<
  NonNullable<UserConfig['lint']>['overrides']
>[number];

const WEB = 'apps/web/';
const WEB_SOURCES = '*.{ts,tsx}';
const MAX_DEPTH = 8;
const NUMBER_PARSING =
  'Use Number() to parse numbers; parseInt only with a radix other than 10.';
const ARRAY_CONSTRUCTOR = 'Use an array literal or Array.from({length}).';
const NUMBER_PARSING_PROPERTIES = [
  {object: 'Number', property: 'parseFloat', message: NUMBER_PARSING},
  {object: 'Number', property: 'parseInt', message: NUMBER_PARSING},
];

// Every restriction but the one on default exports, which the framework's
// configuration and route modules need.
const RESTRICTED_SYNTAX = [
  {
    selector:
      "CallExpression[callee.name='parseInt'][arguments.length<2], CallExpression[callee.name='parseInt'][arguments.1.value=10]",
    message: NUMBER_PARSING,
  },
  {
    selector:
      'Program > VariableDeclaration > VariableDeclarator > ArrowFunctionExpression, Program > ExportNamedDeclaration > VariableDeclaration > VariableDeclarator > ArrowFunctionExpression',
    message: 'Use a function declaration for top-level functions.',
  },
  {selector: "CallExpression[callee.name='Array']", message: ARRAY_CONSTRUCTOR},
  {selector: "NewExpression[callee.name='Array']", message: ARRAY_CONSTRUCTOR},
];

// The web client is self-contained: no import leaves apps/web or names an
// absolute path, and a relative import names its file with the extension,
// which both Vite and Node resolve. A glob cannot resolve a path, so each
// directory depth gets the number of parent steps that would leave it. The
// lookbehind needs JS regex, so this is ESLint's rule, not oxlint's.
function staysInWeb(depth: number): LintOverride {
  return {
    files: [WEB + '*/'.repeat(depth) + WEB_SOURCES],
    rules: {
      'eslint-js/no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              regex: `^(\\.\\./){${String(depth)}}\\.\\.(/|$)`,
              message: 'Imports stay inside apps/web.',
            },
            {regex: '^/', message: 'No absolute imports.'},
            {
              regex: '^\\.\\.?(/.*)?(?<!\\.(ts|tsx|css|json|svg\\?raw))$',
              message: 'A relative import names the file with its extension.',
            },
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
    // Oxlint runs these ESLint plugins for the rules it has not ported.
    jsPlugins: [
      {name: 'eslint-js', specifier: 'oxlint-plugin-eslint'},
      {name: 'jsdoc-js', specifier: 'eslint-plugin-jsdoc'},
      {name: 'shadcn', specifier: '@shadcn/lint'},
    ],
    ignorePatterns: [
      '**/dist/**',
      '**/.react-router/**',
      '**/.wrangler/**',
      'apps/web/addons/**',
      'apps/web/piece_sets/**',
    ],
    options: {typeAware: true, typeCheck: true},
    rules: {
      'block-scoped-var': 'error',
      curly: ['error', 'multi-line'],
      'default-case': 'error',
      eqeqeq: 'error',
      'no-var': 'error',
      'prefer-const': 'error',
      'no-restricted-globals': [
        'error',
        {name: 'parseFloat', message: NUMBER_PARSING},
      ],
      'eslint-js/no-restricted-properties': [
        'error',
        ...NUMBER_PARSING_PROPERTIES,
      ],
      'eslint-js/no-restricted-syntax': [
        'error',
        ...RESTRICTED_SYNTAX,
        {selector: 'ExportDefaultDeclaration', message: 'Use named exports.'},
      ],
      'jsdoc-js/require-jsdoc': [
        'error',
        {
          publicOnly: true,
          require: {
            FunctionDeclaration: true,
            ClassDeclaration: true,
            ArrowFunctionExpression: true,
          },
          contexts: [
            'ExportNamedDeclaration > VariableDeclaration',
            'ExportNamedDeclaration > TSTypeAliasDeclaration',
            'ExportNamedDeclaration > TSInterfaceDeclaration',
          ],
        },
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
    overrides: [
      ...Array.from({length: MAX_DEPTH + 1}, (_, depth) => staysInWeb(depth)),
      {
        files: [
          WEB + 'src/components/**',
          WEB + 'src/lib/auth/**',
          WEB + 'src/lib/utils.ts',
        ],
        rules: {
          'jsdoc-js/require-jsdoc': 'off',
          'typescript/explicit-module-boundary-types': 'off',
          'eslint-js/no-restricted-imports': 'off',
          'eslint-js/no-restricted-syntax': 'off',
          'eslint-js/no-restricted-properties': 'off',
          'max-lines': 'off',
          'max-lines-per-function': 'off',
          eqeqeq: 'off',
          'typescript/consistent-type-assertions': 'off',
          'react/set-state-in-effect': 'off',
          'react/preserve-manual-memoization': 'off',
        },
      },
      {
        // Each generated type alias restates the documented schema above it.
        files: [WEB + 'src/contract/contract.ts'],
        rules: {'jsdoc-js/require-jsdoc': 'off'},
      },
      {
        files: [WEB + 'src/**/*.tsx'],
        excludeFiles: [WEB + 'src/components/**'],
        rules: {
          'shadcn/no-raw-colors': 'error',
          'shadcn/no-arbitrary-values': 'error',
          'shadcn/require-static-classes': 'error',
          'shadcn/no-restyle': 'error',
        },
      },
      {
        // DOM code reads textContent.
        files: [WEB + 'src/**/*.{ts,tsx}'],
        rules: {
          'eslint-js/no-restricted-properties': [
            'error',
            ...NUMBER_PARSING_PROPERTIES,
            {property: 'innerText', message: 'Use textContent.'},
          ],
        },
      },
      {
        // Production code types an object literal by its declaration,
        // `const x: T = {...}`. Tests and their fakes may cast partial objects.
        files: [WEB + 'src/**/*.{ts,tsx}'],
        excludeFiles: [
          WEB + 'src/**/testing/**',
          WEB + 'src/**/*_test.{ts,tsx}',
        ],
        rules: {
          'typescript/consistent-type-assertions': [
            'error',
            {
              assertionStyle: 'as',
              objectLiteralTypeAssertions: 'allow-as-parameter',
            },
          ],
        },
      },
      {
        // The framework requires a default export from these modules.
        files: [
          '**/vite.config.ts',
          WEB + 'react-router.config.ts',
          WEB + 'src/root.tsx',
          WEB + 'src/routes.ts',
          WEB + 'src/routes/*.tsx',
          WEB + 'worker/*.ts',
        ],
        rules: {
          'eslint-js/no-restricted-syntax': ['error', ...RESTRICTED_SYNTAX],
        },
      },
    ],
  },
});
