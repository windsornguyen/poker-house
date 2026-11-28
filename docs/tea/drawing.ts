// Renders the tea corner's pencil drawing as SVG markup, without touching the DOM.
//
// The lines are drawn by hand in view-box units and roughened twice in the browser: a
// displacement filter adds hand tremor and a grain filter breaks each line like graphite
// on paper. The table and chair are also traced a second time, offset by a fraction of a
// unit and fainter, the way a pencil passes over a line twice. Moving parts carry ids
// (all prefixed `tea-`) for `corner.ts` to pose each frame.

/** The visible part of the 200 x 150 scene: x, y, width and height. */
export const VIEW_BOX = '54 46 130 98';

/** The ids of the parts `corner.ts` poses each frame. */
export const PART_IDS = [
  'tea-pitcher',
  'tea-cup',
  'tea-surface',
  'tea-stream',
  'tea-steam',
  'tea-ghost',
  'tea-ghost-arm',
  'tea-eyes-open',
  'tea-eyes-closed',
] as const;

/** One of the ids in PART_IDS. */
export type PartId = (typeof PART_IDS)[number];

/** The lace hem's endpoints, its scallop count, and how far its middle sags. */
const HEM_LEFT = {x: 61.6, y: 91.5};
const HEM_RIGHT = {x: 130.2, y: 91};
const HEM_SCALLOPS = 13;
const HEM_SAG = 4;
/** Fixed so the hand-drawn jitter is the same on every load. */
const JITTER_SEED = 20261127;

/** Returns the whole drawing as one `<svg>` element's markup. */
export function renderTeaScene(): string {
  return [
    `<svg viewBox="${VIEW_BOX}" xmlns="http://www.w3.org/2000/svg" focusable="false">`,
    FILTERS,
    '<g filter="url(#tea-pencil)">',
    `<g id="tea-still">${TABLE}${lace()}${CHAIR}${SAUCER}</g>`,
    '<use href="#tea-still" class="tea-second-pass" transform="translate(0.35 0.25)"/>',
    GHOST,
    PITCHER,
    CUP,
    '<path id="tea-stream" class="tea-stream" pathLength="1" d="M0 0"/>',
    STEAM,
    '</g>',
    '</svg>',
  ].join('');
}

// Tremor: slow noise (one bend every ~3 units) shifts each line by up to 0.4 units. Grain:
// finer noise, turned into an alpha mask by A' = 1.25 − 1.2·A, removes specks from lines.
const FILTERS = [
  '<defs>',
  '<filter id="tea-pencil" x="-10%" y="-10%" width="120%" height="120%">',
  '<feTurbulence type="fractalNoise" baseFrequency="0.35" numOctaves="2" seed="7" result="tremor"/>',
  '<feDisplacementMap in="SourceGraphic" in2="tremor" scale="0.8" xChannelSelector="R" yChannelSelector="G" result="shaken"/>',
  '<feTurbulence type="fractalNoise" baseFrequency="1.6" numOctaves="1" seed="3" result="noise"/>',
  '<feColorMatrix in="noise" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -1.2 1.25" result="grain"/>',
  '<feComposite in="shaken" in2="grain" operator="in"/>',
  '</filter>',
  '</defs>',
].join('');

const TABLE = [
  // The round top, seen from slightly above; the pencil overshoots where it closes.
  line(
    'M60 80.5C60 75 76 71.8 96 71.6C117 71.4 132.5 75 132 80.2C131.6 85 116 88.4 95.5 88.3C76 88.2 60.3 85.2 59.6 79.6C59.5 78.6 60.4 77.6 61.5 77',
  ),
  line('M60.2 81.5C60.4 85 60.8 88.5 61.6 91.5'),
  line('M131.8 81C131.6 84.6 131 88 130.2 91'),
  // The stem, the ring halfway down, and three legs that end in curls.
  line('M94.2 96C94 104 94.4 110 94.1 117'),
  line('M96.2 96C96.4 104 96 110 96.3 117'),
  light(
    'M86 112.6C86.2 110.8 104 110.6 104.2 112.4C104 114.2 86.4 114.4 86 112.6',
  ),
  line(
    'M94.6 117C89 119.5 81.5 126 80 134.5C79.4 138 82.6 139.6 84 137.6C85 136 83.4 134.6 82.2 135.6',
  ),
  line(
    'M95.8 117C101.5 119.5 109.5 126 111 134.5C111.6 138 108.4 139.6 107 137.6C106 136 107.6 134.6 108.8 135.6',
  ),
  light(
    'M95.2 117.5C95.6 124 96 130 95.6 135.5C95.4 137.4 97.6 137.8 97.8 136.2',
  ),
].join('');

const CHAIR = [
  // The tall back, a second wire inside it, and the scrolls at the top.
  line(
    'M146 101C144 90 143.6 74 148.4 64.6C152 57.6 163.8 57.4 167.8 64.4C172.6 73.8 172.2 90 170 100.6',
  ),
  light(
    'M148.4 100.8C146.8 90 146.6 75.4 150.6 66.8C153.6 60.8 162.4 60.6 165.6 66.6C169.4 75 169.2 90 167.6 100.6',
  ),
  line('M151.5 72C148.6 70.6 148.8 66 152.2 65.8C155 65.8 155 69.4 152.6 69.4'),
  line('M164.5 72C167.4 70.6 167.2 66 163.8 65.8C161 65.8 161 69.4 163.4 69.4'),
  // A leaf, not a loop: two scrolls and a loop read as a face.
  light(
    'M158 67.6C156.4 70.8 156.5 74.8 158 77C159.5 74.8 159.6 70.8 158 67.6',
  ),
  // The round seat with its woven zigzag, four legs, and the ring between them.
  line(
    'M143 102C143.2 99.4 172.6 99.2 173 101.8C172.8 104.6 143.4 104.8 143 102',
  ),
  light('M149 101.6l2.2-1.4 1.4 2.2 2.4-2.2 1.4 2.2 2.4-2.2 1.4 2.2 2.2-1.8'),
  line(
    'M145.2 103.6C144.6 113 143.6 124 142.2 134.8C141.8 137.8 144.8 138.6 145.4 136.6',
  ),
  line(
    'M170.8 103.6C171.6 113 172.8 124 174.4 134.8C174.8 137.8 171.8 138.6 171.2 136.6',
  ),
  light('M149.6 101.4C149.8 110 150.2 120 150.8 130.6'),
  light('M166.4 101.4C166.4 110 166 120 165.4 130.6'),
  light(
    'M144.2 120.6C144.6 118.4 172.4 118.4 173 120.6C172.6 122.8 144.8 122.8 144.2 120.6',
  ),
].join('');

const SAUCER = [
  paper(
    'M101.4 79C101.8 77.6 114.2 77.6 114.6 79C114.2 80.6 101.8 80.6 101.4 79Z',
  ),
  line(
    'M101.4 79C101.8 77.6 114.2 77.6 114.6 79C114.2 80.6 101.8 80.6 101.4 79',
  ),
  light('M104.6 78.9C105 78.3 111 78.3 111.4 78.9'),
].join('');

// The pitcher, drawn around its foot at (0, 0) with the spout on the right.
const PITCHER = [
  '<g id="tea-pitcher">',
  paper(
    'M-3.3-1.6C-3.7-5-3.9-9-3.4-12.3C-2-13.3 1.6-13.2 3.2-12.6L3.2-11.8C3.6-8.6 3.5-4.8 3-1.6C1.4-0.9-1.6-0.9-3.3-1.6Z',
  ),
  line('M-3.3-1.6C-3.7-5-3.9-9-3.4-12.3'),
  line('M-3.6-12.5C-2-13.3 1.6-13.2 3.2-12.6C3.8-12.8 4.3-13.3 4.7-13.7'),
  line('M4.7-13.7C4.2-12.6 3.6-12.2 3.2-11.8'),
  line('M3.2-11.8C3.6-8.6 3.5-4.8 3-1.6'),
  line('M-3.3-1.6C-1.6-0.9 1.4-0.9 3-1.6'),
  line('M-0.4-1.2L-0.3 0'),
  line('M-2.3 0.5C-1.2-0.2 1.2-0.2 2.3 0.5C1.2 1.1-1.2 1.1-2.3 0.5'),
  line('M-3.5-11C-6.6-10.6-6.8-5.2-3.7-4.4'),
  light('M-3.5-9.8C-5.4-9.4-5.5-6.2-3.6-5.8'),
  light('M-3.5-9C-1.4-8.4 1.6-8.4 3.4-9'),
  '</g>',
].join('');

// The cup, drawn around the middle of its base at (0, 0), with the tea's surface inside.
const CUP = [
  '<g id="tea-cup">',
  paper(
    'M-4.4-4.6C-4.2-1.8-2.6-0.1 0 0C2.6-0.1 4.2-1.8 4.4-4.6C4.2-5.7-4.2-5.7-4.4-4.6Z',
  ),
  '<ellipse id="tea-surface" class="tea-tea" cx="0" cy="-4.6" rx="3.9" ry="0.75"/>',
  line('M-4.4-4.6C-4.2-1.8-2.6-0.1 0 0C2.6-0.1 4.2-1.8 4.4-4.6'),
  line('M-4.4-4.6C-4.2-5.7 4.2-5.7 4.4-4.6C4.2-3.6-4.2-3.6-4.4-4.6'),
  line('M4.1-3.8C6.4-4.2 6.8-1.4 3.6-1.2'),
  light('M-1.6 0C-1.4 0.5 1.4 0.5 1.6 0'),
  '</g>',
].join('');

const STEAM = [
  '<g id="tea-steam" opacity="0">',
  light(
    'M106.6 71C105.4 68.6 107.6 67 106.6 64.6C105.8 62.8 107 61.2 107.4 60.4',
  ),
  light(
    'M109.6 71.4C110.8 69 108.6 67.4 109.8 65C110.6 63.4 109.6 62 109.2 61',
  ),
  '</g>',
].join('');

// The ghost, drawn around the bottom of its hem at (0, 0): round head with five tufts, dot
// eyes, a ring nose and a small smile, two twig arms, and a short cloak tied with a bow.
const GHOST = [
  '<g id="tea-ghost">',
  '<g class="tea-ghost__bob">',
  '<g class="tea-ghost__cape">',
  '<path class="tea-cloak" d="M-8.6-15.6C-12.2-10.6-13.8-5-14 0.6C-12.6 1.6-11 1.2-9.8-0.4L9.8-0.4C11 1.2 12.6 1.6 14 0.6C13.8-5 12.2-10.6 8.6-15.6Z"/>',
  line('M-8.6-15.6C-12.2-10.6-13.8-5-14 0.6C-12.6 1.6-11 1.2-9.8-0.4'),
  line('M8.6-15.6C12.2-10.6 13.8-5 14 0.6C12.6 1.6 11 1.2 9.8-0.4'),
  light('M-12-8l-1.4 2.2M-12.6-4.4l-1 1.8M12-8l1.4 2.2M12.6-4.4l1 1.8'),
  '</g>',
  paper(
    'M-10-2C-11-10-11.6-18-9.6-24.4C-7.6-30.6-3.6-33.2 0.2-33C4.2-32.8 8.2-30.4 9.9-24.2C11.6-18 11.2-10 10.2-2Q7.8 1.4 5.2-0.9Q2.6 1.5 0-0.7Q-2.6 1.6-5.1-0.8Q-7.6 1.4-10-2Z',
  ),
  line(
    'M-10-2C-11-10-11.6-18-9.6-24.4C-7.6-30.6-3.6-33.2 0.2-33C4.2-32.8 8.2-30.4 9.9-24.2C11.6-18 11.2-10 10.2-2Q7.8 1.4 5.2-0.9Q2.6 1.5 0-0.7Q-2.6 1.6-5.1-0.8Q-7.6 1.4-10-2',
  ),
  line(
    'M0-33.4L0-36.2M5.2-31.8L6.8-34.1M-5.2-31.8L-6.8-34.1M8.2-28.2L10.7-29.4M-8.2-28.2L-10.7-29.4',
  ),
  '<g id="tea-eyes-open"><circle class="tea-dot" cx="-3.8" cy="-22.6" r="0.95"/><circle class="tea-dot" cx="3.8" cy="-22.6" r="0.95"/></g>',
  `<g id="tea-eyes-closed" visibility="hidden">${line('M-5-22.4Q-3.8-21.4-2.6-22.4M2.6-22.4Q3.8-21.4 5-22.4')}</g>`,
  line('M1.7-19.6A1.7 1.7 0 1 1-1.7-19.6A1.7 1.7 0 1 1 1.7-19.6'),
  line('M-3.4-16.4Q0-13.8 3.4-16.4'),
  '<circle class="tea-blush" cx="-6.6" cy="-18" r="1.4"/><circle class="tea-blush" cx="6.6" cy="-18" r="1.4"/>',
  '<circle class="tea-dot" cx="0" cy="-6.2" r="0.45"/>',
  line('M-8.6-15.6Q0-12.6 8.6-15.6'),
  line(
    'M0-14.1C-1.6-15.5-3-14.3-2.2-13.1C-1.6-12.3-0.6-13.1 0-14.1C0.6-13.1 1.6-12.3 2.2-13.1C3-14.3 1.6-15.5 0-14.1M0-14.1L-1-11.5M0-14.1L1.1-11.6',
  ),
  `<g id="tea-ghost-arm">${line('M-10.4-11.6L-13.2-12.8M-11.8-12.2L-12.4-13.8')}</g>`,
  line('M10.4-11.6L13.2-12.8M11.8-12.2L12.4-13.8'),
  '</g>',
  '</g>',
].join('');

/** Returns the lace hem: scallops along a sagging line, with an eyelet above each one. */
function lace(): string {
  const random = seededRandom(JITTER_SEED);
  const width = HEM_RIGHT.x - HEM_LEFT.x;
  const hemY = (x: number): number =>
    HEM_LEFT.y +
    ((HEM_RIGHT.y - HEM_LEFT.y) * (x - HEM_LEFT.x)) / width +
    HEM_SAG * Math.sin((Math.PI * (x - HEM_LEFT.x)) / width);
  const step = width / HEM_SCALLOPS;
  const scallops: string[] = [`M${fixed(HEM_LEFT.x)} ${fixed(HEM_LEFT.y)}`];
  const eyelets: string[] = [];
  for (let index = 0; index < HEM_SCALLOPS; index += 1) {
    const middle = HEM_LEFT.x + step * (index + 0.5);
    const end = HEM_LEFT.x + step * (index + 1);
    const depth = 2 + random() * 1.1;
    scallops.push(
      `Q${fixed(middle + (random() - 0.5) * 0.8)} ${fixed(hemY(middle) + depth)} ${fixed(end)} ${fixed(hemY(end))}`,
    );
    eyelets.push(
      `<circle class="tea-line tea-line--light" cx="${fixed(middle)}" cy="${fixed(hemY(middle) - 1.6 + (random() - 0.5) * 0.5)}" r="${fixed(0.6 + random() * 0.3)}"/>`,
    );
  }
  return line(scallops.join('')) + eyelets.join('');
}

// mulberry32: a 32-bit generator, enough for jitter that must repeat exactly.
function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return (): number => {
    state = (state + 0x6d2b79f5) >>> 0;
    let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
    mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 2 ** 32;
  };
}

function line(d: string): string {
  return `<path class="tea-line" d="${d}"/>`;
}

function light(d: string): string {
  return `<path class="tea-line tea-line--light" d="${d}"/>`;
}

// Paper-colored fill that hides the lines behind a part, as an eraser would.
function paper(d: string): string {
  return `<path class="tea-paper" d="${d}"/>`;
}

function fixed(value: number): string {
  return value.toFixed(2);
}
