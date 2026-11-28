# Tea corner on the docs site

The tea corner is a small pencil drawing in the bottom-right corner of every page of
docs.doggybank.io. It shows a wire bistro table, one wire chair and a ghost. It has no
text. It is decoration for people reading the docs.

## What it shows

- A round wire table with a lace cloth, a small pitcher and a teacup on a saucer, drawn
  in the style of Helen's first reference sketch.
- One wire chair. The ghost floats above its seat when nothing happens.
- One ghost and one cup. The ghost has a round head, five short tufts, dot eyes, a ring
  nose and a small smile (the soft-pencil reference), and wears a small cloak tied with
  a bow.
- Lines are thin and hand-drawn: irregular curves, a light second pass offset by a
  fraction of a pixel, a displacement filter for hand tremor and a grain filter for
  graphite on paper. The tea is a light amber colored-pencil wash.

## Behaviour

- The first scroll, wheel or touch swipe starts one sequence, which plays to the end.
  Scrolling during the sequence does nothing. Scrolling after it ends starts it again.
- Sequence (about 7.3 s): the pitcher lifts and tips, a stream pours and the cup fills,
  steam rises, the ghost floats to the table, the cup rises to the ghost and empties
  while its eyes close, the cup returns, and the ghost floats back to the chair.
- The ghost bobs and its cloak sways slowly while idle.
- With the operating system's reduced-motion setting, the drawing is still.

## Constraints

- At most 1/10 of the screen: 160 px wide at most (12% of the viewport width), about
  3% of a 1360 x 650 screen. Hidden below 768 px width, where it would cover text.
- Hidden from screen readers (`aria-hidden`), ignores the pointer, never blocks reading.
- Follows the docs' light and dark color schemes.
- No new runtime library. TypeScript bundled by esbuild in `docs/build.mts`, loaded
  through Scalar's `head.scripts`; CSS through `head.styles`.

## Approaches

1. Hand-authored SVG animated by a pure timeline in TypeScript (chosen). Every frame is a
   pure function of elapsed time, so the sequence is testable without a browser, and the
   drawing stays sharp at any pixel density.
2. A drawn frame-by-frame sprite (PNG or WebP). Most "human" line quality, but it needs
   dozens of hand-drawn frames and cannot follow the dark theme.
3. A Lottie or Rive animation. Needs an authoring tool and a runtime library for a
   160 px drawing.

Sigil UI is not used. Its bold component style is the opposite of thin pencil.

## Decisions left to the builder

- Exact paths, timings and easings, tuned by eye in the browser.
- Who tips the pitcher: no hands touch it; it lifts by itself, as ghost magic.
