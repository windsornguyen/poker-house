/**
 * Where the red chips sit on the dachshund drawing, in the drawing's own pixels.
 *
 * Every length here is in the source drawing's 2000 x 667 pixel frame, so the
 * chips keep their places as the drawing scales: on screen, a length is
 * multiplied by (rendered width / ART_WIDTH). The stage extends the frame
 * downward to an invisible floor the chips land on.
 */

/** The source drawing's width, in its own pixels. */
export const ART_WIDTH = 2000;
/** The source drawing's height, in its own pixels. */
export const ART_HEIGHT = 667;
/** The lowest pixel of the dog's feet. */
export const FEET_Y = 568;
// 230 source px is 83 px when the dog is 720 px wide: inside the 60-120 px asked for.
/** The floor's middle depth: chips land within FLOOR_SPREAD of it. */
export const FLOOR_Y = FEET_Y + 230;
/** How far nearer or farther than FLOOR_Y a chip may land, so the chips scatter in depth. */
export const FLOOR_SPREAD = 32;
/** The stage: the drawing plus room below for the floor and a chip's bounce. */
export const STAGE_HEIGHT = FLOOR_Y + FLOOR_SPREAD + 40;

/** The chip sprite's width at scale 1 (its SVG view box is 80 x 50). */
export const CHIP_WIDTH = 80;
/** How far a chip's face sits above the next chip's face in a stack, at scale 1. */
export const CHIP_THICKNESS = 16;
/** The sprite's centre lies this far below its face's centre, at scale 1. */
const FACE_TO_CENTER = CHIP_THICKNESS / 2;

/** A tower of red chips: its axis, its top face, its chip count and its sprites' scale. */
export type Tower = Readonly<{
  name: 'tall' | 'short';
  x: number;
  topFaceY: number;
  count: number;
  scale: number;
}>;

// Measured on the drawing: the tall tower stands behind and right of the short one.
/** The tower that wobbles and topples first. */
export const TALL_TOWER: Tower = {
  name: 'tall',
  x: 946.5,
  topFaceY: 350.5,
  count: 3,
  scale: 1.07,
};
/** The tower the tall one falls into. */
export const SHORT_TOWER: Tower = {
  name: 'short',
  x: 910.5,
  topFaceY: 378.5,
  count: 2,
  scale: 0.9,
};

/** One chip at rest: its tower, its place counted from the bottom, and its centre. */
export type RestingChip = Readonly<{
  tower: Tower;
  level: number;
  x: number;
  y: number;
}>;

/**
 * Returns every red chip at rest, in drawing order: the tall tower behind, then
 * the short tower, each from its bottom chip to its top chip.
 */
export function restingChips(): RestingChip[] {
  return [TALL_TOWER, SHORT_TOWER].flatMap(tower =>
    Array.from({length: tower.count}, (_, level) => ({
      tower,
      level,
      x: tower.x,
      y:
        tower.topFaceY +
        (tower.count - 1 - level) * CHIP_THICKNESS * tower.scale +
        FACE_TO_CENTER * tower.scale,
    })),
  );
}
