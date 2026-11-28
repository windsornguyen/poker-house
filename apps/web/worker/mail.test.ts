/** Invariant: only emails asked to carry the dog show it, and every URL is escaped for HTML. */
import {expect, test} from 'vite-plus/test';

import {DOG_PATH, type MailContent, renderMail} from './mail.ts';

const CONFIRM: MailContent = {
  action: 'Confirm your email',
  url: 'https://doggybank.io/api/auth/verify-email?token=abc&callbackURL=/',
  origin: 'https://doggybank.io',
  signOff: 'dog',
};

test('a confirmation email ends with the dog, served from the same site', () => {
  const {html} = renderMail(CONFIRM);

  expect(html).toContain(`<img src="https://doggybank.io${DOG_PATH}"`);
  expect(html.indexOf('<img')).toBeGreaterThan(html.indexOf('</a>'));
});

test('an email without a sign-off has no image', () => {
  const {html} = renderMail({...CONFIRM, signOff: 'none'});

  expect(html).not.toContain('<img');
});

test('the plain-text body names the action and the raw link, with no image', () => {
  const {text} = renderMail(CONFIRM);

  expect(text).toBe(`Confirm your email: ${CONFIRM.url}`);
});

test('quotes and angle brackets in the link cannot break out of the href attribute', () => {
  const {html} = renderMail({
    ...CONFIRM,
    url: 'https://doggybank.io/"><script>x</script>',
  });

  expect(html).not.toContain('<script>');
  expect(html).toContain(
    'href="https://doggybank.io/&quot;&gt;&lt;script&gt;x&lt;/script&gt;"',
  );
});

test('ampersands in the link are escaped once', () => {
  const {html} = renderMail(CONFIRM);

  expect(html).toContain('token=abc&amp;callbackURL=/');
  expect(html).not.toContain('&amp;amp;');
});
