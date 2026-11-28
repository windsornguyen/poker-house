/** Renders one Doggybank email: a single link, signed off by the dog where asked. */

/** Whether an email ends with the dog drawing. */
export type SignOff = 'dog' | 'none';

/** What an email says and where its link goes; `url` and `origin` are untrusted text. */
export type MailContent = Readonly<{
  action: string;
  url: string;
  origin: string;
  signOff: SignOff;
}>;

/** The plain-text and HTML bodies Resend sends together. */
export type MailBody = Readonly<{text: string; html: string}>;

/** The dog drawing in the site's public assets (apps/web/public/email/dog.png). */
export const DOG_PATH = '/email/dog.png';
// The file is 160 x 236 px, drawn at half size so it stays sharp on dense screens.
const DOG_WIDTH_PX = 80;
const DOG_HEIGHT_PX = 118;

const ENTITIES: Readonly<Record<string, string>> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
};

/** Returns the text and HTML bodies for `content`, with every URL escaped for HTML. */
export function renderMail(content: MailContent): MailBody {
  const link = `<p><a href="${escapeHtml(content.url)}">${content.action}</a></p>`;
  return {
    text: `${content.action}: ${content.url}`,
    html: link + signOffHtml(content),
  };
}

function signOffHtml(content: MailContent): string {
  switch (content.signOff) {
    case 'none':
      return '';
    case 'dog':
      return `<p><img src="${escapeHtml(content.origin + DOG_PATH)}" width="${String(DOG_WIDTH_PX)}" height="${String(DOG_HEIGHT_PX)}" alt="Doggybank's dog" style="display:block;border:0"></p>`;
    default:
      return unknownSignOff(content.signOff);
  }
}

function unknownSignOff(signOff: never): never {
  throw new Error(
    `unknown email sign-off \`${String(signOff)}\`; use 'dog' or 'none'`,
  );
}

function escapeHtml(text: string): string {
  return Object.entries(ENTITIES).reduce(
    (escaped, [character, entity]) => escaped.replaceAll(character, entity),
    text,
  );
}
