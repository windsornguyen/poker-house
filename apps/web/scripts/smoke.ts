// Loads pages of a deployed site in a real browser and fails on any script error. A route
// module imported whole hides what the build split apart, so only the browser running the
// built chunks sees a split loader that lost its code. The pages need the real API behind
// them, so this runs against a deployed site.
//
//   node scripts/smoke.ts <site url> [path...]    every page by default
import {type Page, chromium} from 'playwright';

// Signed out, the lobby, admin and table routes all redirect to sign-in after their loaders
// run, so each path exercises a loader.
const PATHS = [
  '/',
  '/auth/sign-in',
  '/auth/sign-up',
  '/admin',
  '/game/doggybank',
] as const;

// The browser reports every failed request on the console. Signed out, the API answers 401,
// and the preview serves no API, so these lines are expected and not script errors.
const FAILED_REQUEST = 'Failed to load resource';

/** The script errors one page raised while loading, by message. */
async function errorsOn(page: Page, url: string): Promise<string[]> {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.stack ?? error.message));
  page.on('console', message => {
    if (
      message.type() === 'error' &&
      !message.text().startsWith(FAILED_REQUEST)
    ) {
      errors.push(message.text());
    }
  });
  await page.goto(url, {waitUntil: 'networkidle'});
  return errors;
}

/** Loads `paths` of `base` as a signed-out visitor, and throws naming each failure. */
async function smoke(base: string, paths: readonly string[]): Promise<void> {
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  const failures: string[] = [];
  try {
    const context = await browser.newContext();
    for (const path of paths) {
      const page = await context.newPage();
      const errors = await errorsOn(page, new URL(path, base).href);
      if (path === '/') {
        // A loader that throws replaces the page with React Router's error screen.
        const signUp = page.getByRole('link', {name: 'Create an account'});
        await signUp
          .first()
          .waitFor({state: 'visible', timeout: 10_000})
          .catch(() => {
            errors.push('the home page never showed "Create an account"');
          });
      }
      await page.close();
      if (errors.length === 0) {
        console.log(`ok ${path}`);
      } else {
        failures.push(`${path}:\n  ${errors.join('\n  ')}`);
      }
    }
    // A session cookie changes what / serves: the app shell, not the landing
    // page. A cookie the server does not accept must still end on a working page.
    const signedIn = await browser.newContext();
    await signedIn.addCookies([
      {
        name: '__Secure-better-auth.session_token',
        value: 'smoke',
        url: new URL('/', base).href,
      },
    ]);
    const page = await signedIn.newPage();
    const errors = await errorsOn(page, new URL('/', base).href);
    await page
      .getByRole('link', {name: 'Create an account'})
      .first()
      .waitFor({state: 'visible', timeout: 10_000})
      .catch(() => {
        errors.push(
          'with a session cookie, / never showed "Create an account"',
        );
      });
    if (errors.length === 0) {
      console.log('ok / with a session cookie');
    } else {
      failures.push(`/ with a session cookie:\n  ${errors.join('\n  ')}`);
    }
  } finally {
    await browser.close();
  }
  if (failures.length > 0) {
    throw new Error(`Pages failed in the browser:\n${failures.join('\n')}`);
  }
}

const [site, ...paths] = process.argv.slice(2);
if (site === undefined || !URL.canParse(site)) {
  throw new Error(`Smoke a site URL, not ${JSON.stringify(site)}.`);
}
await smoke(site, paths.length > 0 ? paths : PATHS);
