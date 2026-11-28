// Computes where every moving part of the tea corner is at a given time, without the DOM.
//
// Coordinates are SVG user units in a 200 x 150 view box; y grows downward and angles are
// degrees clockwise, as SVG `rotate()` reads them. A point p on a part drawn at local
// coordinates (x, y), placed by the pose (px, py, θ), lands at
//   p' = (px + x·cos θ − y·sin θ,  py + x·sin θ + y·cos θ).

/** A position in view-box units. */
export type Point = Readonly<{x: number; y: number}>;

/** Where a part's local origin sits and how far it is turned, in degrees clockwise. */
export type Pose = Readonly<{x: number; y: number; angleDeg: number}>;

/** Every animated value of one frame. Levels and progress values lie in [0, 1]. */
export type TeaFrame = Readonly<{
  pitcher: Pose;
  cup: Pose;
  teaLevel: number;
  stream: Readonly<{head: number; tail: number; start: Point; end: Point}>;
  steam: Readonly<{opacity: number; rise: number}>;
  ghost: Point;
  ghostArmRaise: number;
  ghostEyes: 'open' | 'closed';
}>;

/** Whether the reader allows motion, from `prefers-reduced-motion`. */
export type Motion = 'full' | 'reduced';

/**
 * The sequence rests, waits for its first animation frame, or plays since that frame's
 * timestamp. Starting on a frame timestamp keeps every elapsed time at 0 or more, because
 * a frame's timestamp can be earlier than `performance.now()` read during the event.
 */
export type Playback =
  | Readonly<{kind: 'idle'}>
  | Readonly<{kind: 'starting'}>
  | Readonly<{kind: 'playing'; startedAtMs: number}>;

/** A closed interval of the sequence, in milliseconds from its start. */
type Span = Readonly<{startMs: number; endMs: number}>;

/** The pitcher's spout, in the pitcher's local coordinates (origin at its foot). */
export const SPOUT_LOCAL: Point = {x: 4.6, y: -13.6};
/** The cup rim's centre, in the cup's local coordinates (origin at its base). */
export const CUP_RIM_LOCAL: Point = {x: 0, y: -4.6};
/** The cup rim's right edge, in the cup's local coordinates. */
export const CUP_RIM_EDGE_LOCAL: Point = {x: 4.4, y: -4.6};
/** The ghost's mouth, in the ghost's local coordinates (origin at the bottom of its hem). */
export const GHOST_MOUTH_LOCAL: Point = {x: -2, y: -16};

/** The pitcher standing on the table, left of the cup. */
export const PITCHER_HOME: Pose = {x: 82, y: 79, angleDeg: 0};
/** The pitcher lifted 9 units and tipped, so its spout clears the cup rim by about 5 units. */
export const PITCHER_POURING: Pose = {x: 92, y: 70, angleDeg: 62};
/** The cup standing on its saucer. */
export const CUP_HOME: Pose = {x: 108, y: 78.2, angleDeg: 0};
/** The cup raised and tilted so its rim's right edge meets the ghost's mouth at the table. */
export const CUP_SIPPING: Pose = {x: 119.7, y: 64.7, angleDeg: 40};
/** The ghost floating above the chair's seat. */
export const GHOST_HOME: Point = {x: 158, y: 97};
/** The ghost floating beside the table, right of the cup. */
export const GHOST_AT_TABLE: Point = {x: 128, y: 80};
/** How far the ghost rises above the straight line while it floats between places. */
const GHOST_ARC_HEIGHT = 8;
/** How far the stream ends below the rim's centre, inside the cup. */
const STREAM_DEPTH = 1.5;

/** The whole sequence: pour, drink, and float home, in milliseconds. */
export const SEQUENCE_MS = 7300;

const PITCHER_MOVE_OUT: Span = {startMs: 0, endMs: 500};
const PITCHER_TIP: Span = {startMs: 200, endMs: 700};
const STREAM_HEAD: Span = {startMs: 650, endMs: 950};
const CUP_FILL: Span = {startMs: 800, endMs: 2300};
const STREAM_TAIL: Span = {startMs: 2050, endMs: 2350};
const PITCHER_UNTIP: Span = {startMs: 2300, endMs: 2700};
const PITCHER_MOVE_BACK: Span = {startMs: 2500, endMs: 3000};
const STEAM: Span = {startMs: 2000, endMs: 4200};
const GHOST_APPROACH: Span = {startMs: 2700, endMs: 4000};
const ARM_UP: Span = {startMs: 3900, endMs: 4300};
const CUP_LIFT: Span = {startMs: 4000, endMs: 4500};
const SIP: Span = {startMs: 4500, endMs: 5400};
const CUP_LOWER: Span = {startMs: 5400, endMs: 5900};
const ARM_DOWN: Span = {startMs: 5600, endMs: 5900};
const GHOST_RETURN: Span = {startMs: 5900, endMs: 7200};

/** Returns the frame `elapsedMs` after the sequence starts; at 0 and from SEQUENCE_MS on, the resting frame. */
export function teaFrame(elapsedMs: number): TeaFrame {
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) {
    throw new RangeError(
      `elapsed time ${String(elapsedMs)} ms must be a finite number at least 0`,
    );
  }
  const t = Math.min(elapsedMs, SEQUENCE_MS);
  const pitcher = pitcherPose(t);
  const cup = cupPose(t);
  return {
    pitcher,
    cup,
    teaLevel: teaLevel(t),
    stream: {
      head: eased(t, STREAM_HEAD),
      tail: eased(t, STREAM_TAIL),
      start: place(pitcher, SPOUT_LOCAL),
      end: offset(place(CUP_HOME, CUP_RIM_LOCAL), 0, STREAM_DEPTH),
    },
    steam: {
      opacity: Math.sin(Math.PI * linear(t, STEAM)),
      rise: linear(t, STEAM),
    },
    ghost: ghostPosition(t),
    ghostArmRaise: eased(t, ARM_UP) - eased(t, ARM_DOWN),
    // Closed through the sip's last frame, where the last of the tea goes.
    ghostEyes: t > SIP.startMs && t <= SIP.endMs ? 'closed' : 'open',
  };
}

/** Places a local point on a part with the given pose (see the formula at the top). */
export function place(pose: Pose, local: Point): Point {
  const radians = (pose.angleDeg * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return {
    x: pose.x + local.x * cos - local.y * sin,
    y: pose.y + local.x * sin + local.y * cos,
  };
}

/** Returns the next playback after a scroll, wheel or swipe: only a resting sequence starts. */
export function afterScrollIntent(
  playback: Playback,
  motion: Motion,
): Playback {
  if (motion === 'reduced' || playback.kind !== 'idle') {
    return playback;
  }
  return {kind: 'starting'};
}

/** Returns the playback at the animation frame stamped `frameMs`. */
export function afterTick(playback: Playback, frameMs: number): Playback {
  switch (playback.kind) {
    case 'idle':
      return playback;
    case 'starting':
      return {kind: 'playing', startedAtMs: frameMs};
    case 'playing':
      return frameMs - playback.startedAtMs >= SEQUENCE_MS
        ? {kind: 'idle'}
        : playback;
    default:
      return unreachable(playback);
  }
}

function unreachable(value: never): never {
  throw new Error(`unknown playback ${JSON.stringify(value)}`);
}

function pitcherPose(t: number): Pose {
  const out = eased(t, PITCHER_MOVE_OUT) - eased(t, PITCHER_MOVE_BACK);
  const tip = eased(t, PITCHER_TIP) - eased(t, PITCHER_UNTIP);
  return {
    x: mix(PITCHER_HOME.x, PITCHER_POURING.x, out),
    y: mix(PITCHER_HOME.y, PITCHER_POURING.y, out),
    angleDeg: mix(PITCHER_HOME.angleDeg, PITCHER_POURING.angleDeg, tip),
  };
}

function cupPose(t: number): Pose {
  const lift = eased(t, CUP_LIFT) - eased(t, CUP_LOWER);
  return {
    x: mix(CUP_HOME.x, CUP_SIPPING.x, lift),
    y: mix(CUP_HOME.y, CUP_SIPPING.y, lift),
    angleDeg: mix(CUP_HOME.angleDeg, CUP_SIPPING.angleDeg, lift),
  };
}

// The cup fills fast at first and slows as it nears the rim: 1 − (1 − p)².
function teaLevel(t: number): number {
  const fill = 1 - (1 - linear(t, CUP_FILL)) ** 2;
  return fill * (1 - eased(t, SIP));
}

function ghostPosition(t: number): Point {
  const there = eased(t, GHOST_APPROACH);
  const back = eased(t, GHOST_RETURN);
  const along = there - back;
  const arc = Math.sin(Math.PI * there) + Math.sin(Math.PI * back);
  return {
    x: mix(GHOST_HOME.x, GHOST_AT_TABLE.x, along),
    y: mix(GHOST_HOME.y, GHOST_AT_TABLE.y, along) - GHOST_ARC_HEIGHT * arc,
  };
}

function linear(t: number, span: Span): number {
  return Math.min(
    Math.max((t - span.startMs) / (span.endMs - span.startMs), 0),
    1,
  );
}

// Sine ease in and out: (1 − cos πp) / 2, so every move starts and stops at rest.
function eased(t: number, span: Span): number {
  return (1 - Math.cos(Math.PI * linear(t, span))) / 2;
}

function mix(from: number, to: number, amount: number): number {
  return from + (to - from) * amount;
}

function offset(point: Point, dx: number, dy: number): Point {
  return {x: point.x + dx, y: point.y + dy};
}
