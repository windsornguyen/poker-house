/**
 * Simulates the red chip towers falling off the dachshund's back, without the DOM.
 *
 * Units are the drawing's pixels (see chip-layout.ts) and milliseconds. The
 * sequence is a state machine:
 *   IDLE → WOBBLING (0–200 ms) → TOPPLING (200–550 ms) → FALLING → SETTLING → SETTLED.
 * Wobbling and toppling are choreographed poses, a function of time per chip.
 * At 550 ms each chip leaves with the velocity of its pose plus its own push,
 * and from then on moves by a fixed-step simulation (STEP_MS):
 *   v_y ← v_y + g·dt,  p ← p + v·dt  in the air;
 *   v_y ← −e·v_y on hitting its floor (e = RESTITUTION), resting when |v_y| < BOUNCE_MIN;
 *   v_x ← v_x·exp(−μ·dt) on the floor (μ = FLOOR_FRICTION).
 * A falling chip comes toward the viewer: its scale grows by NEAR_SCALE_GAIN
 * times the fraction of its fall completed.
 */
import {
  CHIP_WIDTH,
  FLOOR_SPREAD,
  FLOOR_Y,
  type RestingChip,
  ART_WIDTH,
  restingChips,
} from './chip-layout.ts';

/** The stages of one tumble, in the only order they occur. */
export const TUMBLE_PHASES = [
  'IDLE',
  'WOBBLING',
  'TOPPLING',
  'FALLING',
  'SETTLING',
  'SETTLED',
] as const;

/** One of TUMBLE_PHASES. */
export type TumblePhase = (typeof TUMBLE_PHASES)[number];

/** Whether a chip is in flight or touching the floor. */
export type Contact = 'air' | 'floor';

/** One chip's state: drawing pixels, pixels per ms, degrees, and degrees per ms. */
export type Chip = Readonly<{
  x: number;
  y: number;
  vx: number;
  vy: number;
  rotZ: number;
  vRotZ: number;
  flip: number;
  vFlip: number;
  scale: number;
  baseScale: number;
  depth: number;
  contact: Contact;
  settled: boolean;
  bounces: number;
  rollMs: number;
  launchY: number;
  floorY: number;
}>;

/** A chip's own randomness, drawn once per tumble so no two chips move alike. */
type Temper = Readonly<{
  phase: number;
  lean: number;
  slide: number;
  launchVx: number;
  launchVy: number;
  spin: number;
  flipRate: number;
  floorY: number;
}>;

/** The whole tumble: its phase, its clock, and each chip with its temper. */
export type Tumble = Readonly<{
  phase: TumblePhase;
  elapsedMs: number;
  pendingMs: number;
  tempers: readonly Temper[];
  chips: readonly Chip[];
}>;

/** When wobbling gives way to toppling. */
export const WOBBLE_END_MS = 200;
/** When toppling gives way to free fall. */
export const TOPPLE_END_MS = 550;
// The tall tower's top chips reach the short tower at this moment.
const COLLIDE_MS = 380;
/** The simulation's fixed step; frames of any length are split into these. */
export const STEP_MS = 4;
// A frame longer than this (a hidden tab) advances the tumble by this much only.
const MAX_FRAME_MS = 50;
/** After this long every chip is put at rest, however it moves. */
export const MAX_TUMBLE_MS = 5000;

// Gravity lands a chip launched at 550 ms near 1100 ms: 410 px in 550 ms.
const GRAVITY = 0.0025;
const RESTITUTION = 0.42;
const BOUNCE_MIN = 0.12;
const IMPACT_FRICTION = 0.8;
const IMPACT_SPIN_KEEP = 0.55;
const FLOOR_FRICTION = 0.006;
const AIR_SPIN_DAMPING = 0.0004;
const NEAR_SCALE_GAIN = 0.3;
// A chip landing on its edge rolls this long before it falls flat.
const ROLL_MS = 260;
const ROLL_SPIN = 4;
const FLATTEN_RATE = 0.012;
const REST_TILT_DEG = 8;
const REST_SPEED = 0.003;
const REST_ANGLE_DEG = 0.5;
// Two chips on the floor stay this fraction of their widths apart.
const FLOOR_GAP = 0.75;
const FLOOR_NEIGHBOUR_DEPTH = 40;
// Overlaps smaller than this are rounding left by the last push, not contact.
const OVERLAP_EPSILON = 0.01;
const TALL_LEAN_DEG = 36;

/** Returns the chips at rest on the dog's back. */
export function idleTumble(): Tumble {
  return {
    phase: 'IDLE',
    elapsedMs: 0,
    pendingMs: 0,
    tempers: [],
    chips: restingChips().map(rest => restingChip(rest)),
  };
}

/** Starts a tumble from rest; a tumble already under way is returned unchanged. */
export function startTumble(tumble: Tumble, seed: number): Tumble {
  if (tumble.phase !== 'IDLE') return tumble;
  const random = seededRandom(seed);
  const rests = restingChips();
  const tempers = rests.map((_, index) => drawTemper(random, index));
  return {...tumble, phase: 'WOBBLING', tempers};
}

/** Advances the tumble by `dtMs`; frames longer than MAX_FRAME_MS count as MAX_FRAME_MS. */
export function stepTumble(tumble: Tumble, dtMs: number): Tumble {
  if (!Number.isFinite(dtMs) || dtMs < 0) {
    throw new RangeError(
      `frame time ${String(dtMs)} ms must be a finite number at least 0`,
    );
  }
  if (tumble.phase === 'IDLE' || tumble.phase === 'SETTLED') return tumble;
  let state: Tumble = {
    ...tumble,
    pendingMs: tumble.pendingMs + Math.min(dtMs, MAX_FRAME_MS),
  };
  while (state.pendingMs >= STEP_MS && state.phase !== 'SETTLED') {
    state = advance({...state, pendingMs: state.pendingMs - STEP_MS});
  }
  return state;
}

/** Plays a whole tumble at once and returns it settled; used when motion is reduced. */
export function settledTumble(seed: number): Tumble {
  let state = startTumble(idleTumble(), seed);
  while (state.phase !== 'SETTLED') state = advance(state);
  return state;
}

function advance(tumble: Tumble): Tumble {
  const elapsedMs = tumble.elapsedMs + STEP_MS;
  const rests = restingChips();
  if (elapsedMs < TOPPLE_END_MS) {
    const chips = rests.map((rest, index) =>
      posedChip(rest, temperAt(tumble, index), elapsedMs),
    );
    const phase = elapsedMs < WOBBLE_END_MS ? 'WOBBLING' : 'TOPPLING';
    return {...tumble, phase, elapsedMs, chips};
  }
  const launched =
    tumble.elapsedMs < TOPPLE_END_MS
      ? rests.map((rest, index) =>
          launchedChip(rest, temperAt(tumble, index), elapsedMs),
        )
      : tumble.chips;
  const moved = separateOnFloor(launched.map(chip => movedChip(chip)));
  const chips =
    elapsedMs >= MAX_TUMBLE_MS ? moved.map(chip => restedChip(chip)) : moved;
  return {...tumble, phase: phaseOf(chips), elapsedMs, chips};
}

function phaseOf(chips: readonly Chip[]): TumblePhase {
  if (chips.every(chip => chip.settled)) return 'SETTLED';
  const allLanded = chips.every(
    chip => chip.bounces > 0 || chip.contact === 'floor',
  );
  return allLanded ? 'SETTLING' : 'FALLING';
}

function temperAt(tumble: Tumble, index: number): Temper {
  const temper = tumble.tempers[index];
  if (temper === undefined) {
    throw new Error(
      `chip ${String(index)} has no temper; start the tumble first`,
    );
  }
  return temper;
}

function drawTemper(random: () => number, index: number): Temper {
  const between = (low: number, high: number): number =>
    low + (high - low) * random();
  // Alternate chips flip end over end; the others spin flat.
  const flips = index % 2 === 0;
  return {
    phase: between(0, 2 * Math.PI),
    lean: between(-1, 1),
    slide: between(-1, 1),
    launchVx: between(-0.5, 0.42),
    launchVy: between(0.03, 0.12),
    spin: between(-0.25, 0.25),
    flipRate: flips
      ? between(0.45, 0.9) * (random() < 0.5 ? -1 : 1)
      : between(-0.06, 0.06),
    floorY: FLOOR_Y + between(-FLOOR_SPREAD, FLOOR_SPREAD),
  };
}

function restingChip(rest: RestingChip): Chip {
  return {
    x: rest.x,
    y: rest.y,
    vx: 0,
    vy: 0,
    rotZ: 0,
    vRotZ: 0,
    flip: 0,
    vFlip: 0,
    scale: rest.tower.scale,
    baseScale: rest.tower.scale,
    depth: 0,
    contact: 'air',
    settled: false,
    bounces: 0,
    rollMs: 0,
    launchY: rest.y,
    floorY: rest.y,
  };
}

/** A chip's choreographed place and tilt at `t` ms, before it is released. */
type Pose = Readonly<{x: number; y: number; rotZ: number}>;

function pose(rest: RestingChip, temper: Temper, t: number): Pose {
  return rest.tower.name === 'tall'
    ? tallPose(rest, temper, t)
    : shortPose(rest, temper, t);
}

// The tall tower: a wobble that climbs the tower, then a lean onto the short tower
// about the tower's bottom-left corner, with each chip sliding off the one below.
function tallPose(rest: RestingChip, temper: Temper, t: number): Pose {
  const level = rest.level;
  const start = Math.min(Math.max((t - 30 * level) / 70, 0), 1);
  const fade = 1 - topple(t);
  const shake = start * fade * Math.sin((2 * Math.PI * t) / 95 + temper.phase);
  const tilt = start * fade * Math.sin((2 * Math.PI * t) / 120 + temper.phase);
  const wobbleX = shake * (level === 0 ? 3 : 1.2 + 0.8 * level);
  const wobbleRot = tilt * (level % 2 === 0 ? 1 : -1) * (1.5 + 1.2 * level);
  const u = topple(t);
  const leanDeg = -TALL_LEAN_DEG * u * u * (1 + 0.1 * temper.lean);
  const pivot = {
    x: rest.tower.x - 30 * rest.tower.scale,
    y: rest.y + 16 + 12 * level,
  };
  const turned = rotate({x: rest.x - pivot.x, y: rest.y - pivot.y}, leanDeg);
  return {
    x:
      pivot.x +
      turned.x +
      wobbleX -
      level * 10 * u * u * (1 + 0.4 * temper.slide),
    y: pivot.y + turned.y - level * 1.5 * u,
    rotZ: leanDeg * (0.75 + 0.12 * level + 0.2 * temper.lean) + wobbleRot,
  };
}

// The short tower stands still until the tall tower's chips strike it.
function shortPose(rest: RestingChip, temper: Temper, t: number): Pose {
  const hit = Math.min(
    Math.max((t - COLLIDE_MS) / (TOPPLE_END_MS - COLLIDE_MS), 0),
    1,
  );
  const level = rest.level;
  return {
    x: rest.x - (6 + 7 * level) * hit * hit * (1 + 0.2 * temper.slide),
    y: rest.y - 1.5 * level * hit,
    rotZ: -(8 + 10 * level) * hit * hit * (1 + 0.2 * temper.lean),
  };
}

function topple(t: number): number {
  return Math.min(
    Math.max((t - WOBBLE_END_MS) / (TOPPLE_END_MS - WOBBLE_END_MS), 0),
    1,
  );
}

function posedChip(rest: RestingChip, temper: Temper, t: number): Chip {
  const at = pose(rest, temper, t);
  return {...restingChip(rest), x: at.x, y: at.y, rotZ: at.rotZ};
}

// At release a chip keeps its choreographed velocity, measured over one step, and
// gains its own push toward the viewer: down the screen, left or right, and a spin.
function launchedChip(rest: RestingChip, temper: Temper, t: number): Chip {
  const now = pose(rest, temper, t);
  const before = pose(rest, temper, t - STEP_MS);
  return {
    ...restingChip(rest),
    x: now.x,
    y: now.y,
    rotZ: now.rotZ,
    vx: (now.x - before.x) / STEP_MS + temper.launchVx,
    vy: (now.y - before.y) / STEP_MS + temper.launchVy,
    vRotZ: (now.rotZ - before.rotZ) / STEP_MS + temper.spin,
    vFlip: temper.flipRate,
    launchY: now.y,
    floorY: temper.floorY,
  };
}

function movedChip(chip: Chip): Chip {
  if (chip.settled) return chip;
  return chip.contact === 'air' ? flyingChip(chip) : slidingChip(chip);
}

function flyingChip(chip: Chip): Chip {
  const vy = chip.vy + GRAVITY * STEP_MS;
  const damping = Math.exp(-AIR_SPIN_DAMPING * STEP_MS);
  const moved: Chip = {
    ...chip,
    vy,
    x: clampX(chip.x + chip.vx * STEP_MS),
    y: chip.y + vy * STEP_MS,
    rotZ: chip.rotZ + chip.vRotZ * STEP_MS,
    flip: chip.flip + chip.vFlip * STEP_MS,
    vRotZ: chip.vRotZ * damping,
    vFlip: chip.vFlip * damping,
  };
  const depth = Math.max(chip.depth, depthOf(moved));
  const scaled = {
    ...moved,
    depth,
    scale: chip.baseScale * (1 + NEAR_SCALE_GAIN * depth),
  };
  return scaled.y >= scaled.floorY && vy > 0 ? landedChip(scaled) : scaled;
}

function landedChip(chip: Chip): Chip {
  const bounceVy = -chip.vy * RESTITUTION;
  const resting = Math.abs(bounceVy) < BOUNCE_MIN;
  return {
    ...chip,
    y: chip.floorY,
    vy: resting ? 0 : bounceVy,
    vx: chip.vx * IMPACT_FRICTION,
    vRotZ: resting ? 0 : chip.vRotZ * IMPACT_SPIN_KEEP,
    vFlip: resting ? 0 : chip.vFlip * IMPACT_SPIN_KEEP,
    contact: resting ? 'floor' : 'air',
    bounces: chip.bounces + 1,
  };
}

// On the floor a chip slides to a stop; one that landed on its edge rolls first,
// then falls flat, and its tilt eases into a small resting angle.
function slidingChip(chip: Chip): Chip {
  const vx = chip.vx * Math.exp(-FLOOR_FRICTION * STEP_MS);
  const onEdge = Math.abs(Math.sin((chip.flip * Math.PI) / 180)) > 0.6;
  const rolling = onEdge && chip.rollMs < ROLL_MS;
  const flatFlip = 180 * Math.round(chip.flip / 180);
  const restTilt = Math.min(
    Math.max(wrapDegrees(chip.rotZ), -REST_TILT_DEG),
    REST_TILT_DEG,
  );
  const ease = Math.min(1, FLATTEN_RATE * STEP_MS);
  const flip = rolling ? chip.flip : chip.flip + (flatFlip - chip.flip) * ease;
  const rotZ = rolling
    ? chip.rotZ + vx * ROLL_SPIN * STEP_MS
    : wrapDegrees(chip.rotZ) + (restTilt - wrapDegrees(chip.rotZ)) * ease;
  const moved: Chip = {
    ...chip,
    vx,
    x: clampX(chip.x + vx * STEP_MS),
    flip,
    rotZ,
    rollMs: rolling ? chip.rollMs + STEP_MS : chip.rollMs,
  };
  const still =
    !rolling &&
    Math.abs(vx) < REST_SPEED &&
    Math.abs(flatFlip - flip) < REST_ANGLE_DEG &&
    Math.abs(restTilt - rotZ) < REST_ANGLE_DEG;
  return still ? restedChip(moved) : moved;
}

function restedChip(chip: Chip): Chip {
  const tilt = Math.min(
    Math.max(wrapDegrees(chip.rotZ), -REST_TILT_DEG),
    REST_TILT_DEG,
  );
  return {
    ...chip,
    y: chip.floorY,
    vx: 0,
    vy: 0,
    vRotZ: 0,
    vFlip: 0,
    flip: 180 * Math.round(chip.flip / 180),
    rotZ: tilt,
    depth: 1,
    scale: chip.baseScale * (1 + NEAR_SCALE_GAIN),
    contact: 'floor',
    settled: true,
  };
}

// Chips on the floor at about the same depth push apart until they no longer
// overlap, sharing their sideways speed, so they scatter instead of piling up.
function separateOnFloor(chips: readonly Chip[]): Chip[] {
  const result = [...chips];
  for (let left = 0; left < result.length; left += 1) {
    for (let right = left + 1; right < result.length; right += 1) {
      const a = result[left];
      const b = result[right];
      if (a === undefined || b === undefined) continue;
      const pushed = pushApart(a, b);
      if (pushed === null) continue;
      [result[left], result[right]] = pushed;
    }
  }
  return result;
}

function pushApart(a: Chip, b: Chip): [Chip, Chip] | null {
  const nearFloor = (chip: Chip): boolean => chip.floorY - chip.y < 20;
  const neighbours =
    nearFloor(a) &&
    nearFloor(b) &&
    Math.abs(a.floorY - b.floorY) < FLOOR_NEIGHBOUR_DEPTH;
  const gap = (FLOOR_GAP * CHIP_WIDTH * (a.scale + b.scale)) / 2;
  const dx = b.x - a.x;
  if (!neighbours || gap - Math.abs(dx) < OVERLAP_EPSILON) return null;
  const direction = dx === 0 ? 1 : Math.sign(dx);
  const overlap = (gap - Math.abs(dx)) / 2;
  const sharedVx = (a.vx + b.vx) / 2;
  return [
    {...a, x: clampX(a.x - direction * overlap), vx: sharedVx, settled: false},
    {...b, x: clampX(b.x + direction * overlap), vx: sharedVx, settled: false},
  ];
}

function depthOf(chip: Chip): number {
  const fall = chip.floorY - chip.launchY;
  if (fall <= 0) return 0;
  return Math.min(Math.max((chip.y - chip.launchY) / fall, 0), 1);
}

function clampX(x: number): number {
  return Math.min(Math.max(x, CHIP_WIDTH), ART_WIDTH - CHIP_WIDTH);
}

function wrapDegrees(degrees: number): number {
  return ((((degrees + 180) % 360) + 360) % 360) - 180;
}

function rotate(
  point: Readonly<{x: number; y: number}>,
  degrees: number,
): {x: number; y: number} {
  const radians = (degrees * Math.PI) / 180;
  return {
    x: point.x * Math.cos(radians) - point.y * Math.sin(radians),
    y: point.x * Math.sin(radians) + point.y * Math.cos(radians),
  };
}

// mulberry32: a 32-bit generator; the same seed gives the same tumble.
function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return (): number => {
    state = (state + 0x6d2b79f5) >>> 0;
    let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
    mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 2 ** 32;
  };
}
