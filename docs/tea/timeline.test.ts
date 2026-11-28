// Invariants of the tea corner's sequence: it starts and ends at rest, pours only from a
// tipped pitcher into the cup, and brings the cup to the ghost's mouth.
import {expect, test} from 'vite-plus/test';

import {
  CUP_RIM_EDGE_LOCAL,
  CUP_RIM_LOCAL,
  GHOST_AT_TABLE,
  GHOST_HOME,
  GHOST_MOUTH_LOCAL,
  PITCHER_HOME,
  type Playback,
  type Point,
  SEQUENCE_MS,
  type TeaFrame,
  afterScrollIntent,
  afterTick,
  place,
  teaFrame,
} from './timeline.ts';

const STEP_MS = 10;
/** Digits after the point that `toBeCloseTo` compares: equal to within 5e-10. */
const DIGITS = 9;
/** Units within which the rim counts as touching the mouth; the ghost's lips are 1 unit thick. */
const MOUTH_REACH = 1;
/** Half the cup rim's width: the stream must land closer than this to the rim's centre. */
const RIM_HALF_WIDTH = CUP_RIM_EDGE_LOCAL.x;
/** Half of the pitcher's pouring angle, in degrees. */
const HALF_POUR_DEG = 31;

type Sample = Readonly<{elapsedMs: number; frame: TeaFrame}>;

function everyFrame(): readonly Sample[] {
  return Array.from({length: SEQUENCE_MS / STEP_MS + 1}, (_, index) => {
    const elapsedMs = index * STEP_MS;
    return {elapsedMs, frame: teaFrame(elapsedMs)};
  });
}

function distance(left: Point, right: Point): number {
  return Math.hypot(left.x - right.x, left.y - right.y);
}

function expectAtRest(frame: TeaFrame): void {
  expect(frame.pitcher).toEqual(PITCHER_HOME);
  expect(frame.cup.angleDeg).toBe(0);
  expect(frame.teaLevel).toBe(0);
  expect(frame.stream.head - frame.stream.tail).toBe(0);
  expect(frame.steam.opacity).toBeCloseTo(0, DIGITS);
  expect(distance(frame.ghost, GHOST_HOME)).toBeCloseTo(0, DIGITS);
  expect(frame.ghostArmRaise).toBeCloseTo(0, DIGITS);
  expect(frame.ghostEyes).toBe('open');
}

test('the sequence starts and ends at rest, so a replay begins without a jump', () => {
  expectAtRest(teaFrame(0));
  expectAtRest(teaFrame(SEQUENCE_MS));
  expectAtRest(teaFrame(SEQUENCE_MS * 3));
});

test('every animated value stays inside its range on every frame', () => {
  for (const {frame} of everyFrame()) {
    for (const value of [
      frame.teaLevel,
      frame.stream.head,
      frame.stream.tail,
      frame.ghostArmRaise,
    ]) {
      expect(value).toBeGreaterThanOrEqual(-1e-12);
      expect(value).toBeLessThanOrEqual(1 + 1e-12);
    }
    expect(frame.stream.tail).toBeLessThanOrEqual(frame.stream.head);
  }
});

test('tea flows only while the pitcher is tipped past half its pouring angle', () => {
  const pouring = everyFrame().filter(
    ({frame}) => frame.stream.head - frame.stream.tail > 0,
  );

  expect(pouring.length).toBeGreaterThan(0);
  for (const {frame} of pouring) {
    expect(frame.pitcher.angleDeg).toBeGreaterThan(HALF_POUR_DEG);
  }
});

test('the cup only fills while the stream flows and only empties while the ghost sips', () => {
  const frames = everyFrame();
  const changes = frames.slice(1).map((sample, index) => ({
    sample,
    change:
      sample.frame.teaLevel - (frames[index]?.frame.teaLevel ?? Number.NaN),
  }));
  const filling = changes.filter(({change}) => change > 1e-12);
  const emptying = changes.filter(({change}) => change < -1e-12);

  expect(filling.length).toBeGreaterThan(0);
  expect(emptying.length).toBeGreaterThan(0);
  for (const {sample} of filling) {
    expect(sample.frame.stream.head).toBeGreaterThan(0);
  }
  for (const {sample} of emptying) {
    expect(sample.frame.ghostEyes).toBe('closed');
  }
});

test('the stream leaves the spout above the cup and lands within the rim', () => {
  const pouring = everyFrame().find(
    ({frame}) => frame.stream.head === 1 && frame.stream.tail === 0,
  );
  if (pouring === undefined) {
    throw new Error('no frame shows the whole stream');
  }

  const {start, end} = pouring.frame.stream;
  const rim = place(pouring.frame.cup, CUP_RIM_LOCAL);

  expect(start.y).toBeLessThan(rim.y);
  expect(Math.abs(end.x - rim.x)).toBeLessThan(RIM_HALF_WIDTH);
});

test('while the ghost sips, the tilted rim touches its mouth', () => {
  const sipping = everyFrame().filter(
    ({frame}) => frame.ghostEyes === 'closed',
  );

  expect(sipping.length).toBeGreaterThan(0);
  for (const {frame} of sipping) {
    const mouth = place({...frame.ghost, angleDeg: 0}, GHOST_MOUTH_LOCAL);
    expect(distance(frame.ghost, GHOST_AT_TABLE)).toBeCloseTo(0, DIGITS);
    expect(distance(mouth, place(frame.cup, CUP_RIM_EDGE_LOCAL))).toBeLessThan(
      MOUTH_REACH,
    );
  }
});

test('a negative or non-finite elapsed time is rejected with the value in the message', () => {
  for (const elapsedMs of [-1, Number.NaN, Number.POSITIVE_INFINITY]) {
    expect(() => teaFrame(elapsedMs)).toThrow(
      new RangeError(
        `elapsed time ${String(elapsedMs)} ms must be a finite number at least 0`,
      ),
    );
  }
});

test('a scroll starts a resting sequence, and scrolls during it do not restart it', () => {
  const starting = afterScrollIntent({kind: 'idle'}, 'full');
  const playing = afterTick(starting, 1000);

  expect(starting).toEqual({kind: 'starting'});
  expect(playing).toEqual({kind: 'playing', startedAtMs: 1000});
  expect(afterScrollIntent(starting, 'full')).toEqual(starting);
  expect(afterScrollIntent(playing, 'full')).toEqual(playing);
});

// Invariant: the clock starts on a frame timestamp, so elapsed time is never negative.
// Witness: a frame stamped 1.3 ms before the scroll event that requested it. Starting on
// `performance.now()` read in the event gave -1.3 ms, threw, and left the corner stuck.
test('the first frame after a scroll is at elapsed 0 even when it is stamped before the scroll', () => {
  const frameStampMs = 998.7;

  const playing = afterTick(
    afterScrollIntent({kind: 'idle'}, 'full'),
    frameStampMs,
  );
  if (playing.kind !== 'playing') {
    throw new Error(`expected a playing sequence, got ${playing.kind}`);
  }

  expect(frameStampMs - playing.startedAtMs).toBe(0);
  expect(() => teaFrame(frameStampMs - playing.startedAtMs)).not.toThrow();
});

test('a sequence rests once it has played its full length, and the next scroll replays it', () => {
  const playing: Playback = {kind: 'playing', startedAtMs: 1000};

  const almost = afterTick(playing, 1000 + SEQUENCE_MS - 1);
  const finished = afterTick(playing, 1000 + SEQUENCE_MS);
  const replayed = afterTick(afterScrollIntent(finished, 'full'), 9000);

  expect(almost).toEqual(playing);
  expect(finished).toEqual({kind: 'idle'});
  expect(replayed).toEqual({kind: 'playing', startedAtMs: 9000});
});

test('with reduced motion, a scroll never starts the sequence', () => {
  expect(afterScrollIntent({kind: 'idle'}, 'reduced')).toEqual({kind: 'idle'});
});
