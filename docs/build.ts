// Renders the docs into docs/dist as a static site, with the Scalar CLI's own renderer:
// the same pages Scalar would host, served from our own domain at no cost.
import {type ExecFileSyncOptions, execFileSync} from 'node:child_process';
import {
  cpSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import {homedir} from 'node:os';
import {join, resolve} from 'node:path';

import {build as bundle} from 'esbuild';

/**
 * Runs a Scalar CLI step with node, printing nothing unless it fails. Its progress and its
 * errors both go to stdout, so the output is kept and shown only when the step fails.
 */
function quietly(args: readonly string[], options: ExecFileSyncOptions): void {
  try {
    execFileSync(process.execPath, args, {
      ...options,
      stdio: 'pipe',
      maxBuffer: 1 << 26,
    });
  } catch (error) {
    const {stdout, stderr} = error as {stdout?: Buffer; stderr?: Buffer};
    process.stderr.write(stdout ?? '');
    process.stderr.write(stderr ?? '');
    throw error;
  }
}

const docs = import.meta.dirname;
const output = join(docs, 'dist');
const cli = resolve(docs, '../node_modules/@scalar/cli/index.js');
const isolate = join(homedir(), '.scalar/isolate');

// The tea corner is TypeScript; the page loads the one bundled module that
// scalar.config.json names under head.scripts.
await bundle({
  entryPoints: [join(docs, 'tea/corner.ts')],
  outfile: join(docs, 'tea/dist/corner.js'),
  bundle: true,
  format: 'esm',
  target: 'es2022',
  minify: true,
  logLevel: 'warning',
});

quietly([cli, 'project', 'download-isolate', '--no-input'], {});

// The renderer resolves its bundled packages from ancestors of the build directory.
const build = mkdtempSync(join(isolate, 'doggybank-docs-'));
try {
  quietly([join(isolate, 'dist/isolate-entry.js')], {
    cwd: isolate,
    input: JSON.stringify({
      configPath: 'scalar.config.json',
      projectDir: docs,
      buildDir: build,
      mode: 'build',
      domain: 'docs.doggybank.io',
      baseUrl: 'https://services.scalar.com',
      registryBaseUrl: 'https://registry.scalar.com',
      token: '',
      previewServerPort: 7970,
      logLevel: 'info',
    }),
  });
  rmSync(output, {recursive: true, force: true});
  cpSync(join(build, 'dist'), output, {recursive: true});

  // Scalar also writes rules for URL fragments, which never reach a server. Cloudflare
  // reads each as its bare path and refuses the duplicates, so only path rules are kept.
  const redirects = join(output, '_redirects');
  const rules = readFileSync(redirects, 'utf8').split('\n');
  writeFileSync(
    redirects,
    rules.filter(rule => !rule.split(' ')[0]?.includes('#')).join('\n'),
  );
} finally {
  rmSync(build, {recursive: true, force: true});
}
