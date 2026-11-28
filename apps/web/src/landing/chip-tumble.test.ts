/** Invariant: one disturbance topples the red towers once, and every chip comes to rest on the floor. */
import {expect, test} from 'vite-plus/test';

import {ART_WIDTH, FLOOR_SPREAD, FLOOR_Y, restingChips} from './chip-layout.ts';
import {
  MAX_TUMBLE_MS,
  TOPPLE_END_MS,
  TUMBLE_PHASES,
  type Tumble,
  WOBBLE_END_MS,
  idleTumble,
  settledTumble,
  startTumble,
  stepTumble,
} from './chip-tumble.ts';

const FRAME_MS = 16;
const SEEDS = Array.from({length: 12}, (_, index) => index * 7919 + 1);

function play(seed: number, frameMs = FRAME_MS): Tumble[] {
  const frames = [startTumble(idleTumble(), seed)];
  let last = frames[0];
  while (last !== undefined && last.phase !== 'SETTLED') {
    last = stepTumble(last, frameMs);
    frames.push(last);
    if (last.elapsedMs > MAX_TUMBLE_MS) {
      throw new Error('the tumble never settled');
    }
  }
  return frames;
}

function finalChips(frames: readonly Tumble[]): Tumble['chips'] {
  const last = frames.at(-1);
  if (last === undefined) throw new Error('no frames');
  return last.chips;
}

test('at rest the chips stand in their towers and stepping does nothing', () => {
  const idle = idleTumble();

  expect(idle.phase).toBe('IDLE');
  expect(idle.chips.map(chip => [chip.x, chip.y])).toEqual(
    restingChips().map(rest => [rest.x, rest.y]),
  );
  expect(stepTumble(idle, 500)).toBe(idle);
});

test('a second disturbance while the chips tumble does not restart them', () => {
  const started = stepTumble(startTumble(idleTumble(), 1), 300);

  expect(startTumble(started, 2)).toBe(started);
});

test('the phases occur once each, in order, at the choreographed times', () => {
  for (const seed of SEEDS) {
    const frames = play(seed);
    const order = frames
      .map(frame => frame.phase)
      .filter((phase, index, all) => phase !== all[index - 1]);

    expect(['IDLE', ...order]).toEqual([...TUMBLE_PHASES]);
    for (const frame of frames) {
      if (frame.elapsedMs > 0 && frame.elapsedMs < WOBBLE_END_MS) {
        expect(frame.phase).toBe('WOBBLING');
      }
      if (frame.elapsedMs >= WOBBLE_END_MS && frame.elapsedMs < TOPPLE_END_MS) {
        expect(frame.phase).toBe('TOPPLING');
      }
    }
  }
});

test('every tumble settles naturally between 1.5 s and 3 s, well before the cap', () => {
  for (const seed of SEEDS) {
    const settledAt = play(seed).at(-1)?.elapsedMs ?? Number.NaN;

    expect(settledAt).toBeGreaterThan(1500);
    expect(settledAt).toBeLessThan(3000);
  }
});

test('the short tower stands still until the tall tower strikes it', () => {
  const rests = restingChips();
  const shortIndexes = rests.flatMap((rest, index) =>
    rest.tower.name === 'short' ? [index] : [],
  );
  for (const frame of play(5).filter(frame => frame.elapsedMs <= 380)) {
    for (const index of shortIndexes) {
      expect(frame.chips[index]?.x).toBe(rests[index]?.x);
      expect(Math.abs(frame.chips[index]?.rotZ ?? Number.NaN)).toBe(0);
    }
  }
});

test('while wobbling, the tall tower shifts by only a few pixels', () => {
  const rests = restingChips();
  for (const frame of play(9).filter(frame => frame.phase === 'WOBBLING')) {
    for (const [index, chip] of frame.chips.entries()) {
      expect(Math.abs(chip.x - (rests[index]?.x ?? Number.NaN))).toBeLessThan(
        5,
      );
    }
  }
});

test('the first chip reaches the floor near 1.1 s, after the fall begins', () => {
  for (const seed of SEEDS) {
    const firstLanding = play(seed).find(frame =>
      frame.chips.some(chip => chip.bounces > 0),
    );

    expect(firstLanding?.elapsedMs).toBeGreaterThan(900);
    expect(firstLanding?.elapsedMs).toBeLessThan(1300);
  }
});

test('no chip ever passes below its floor', () => {
  for (const seed of SEEDS) {
    for (const frame of play(seed)) {
      for (const chip of frame.chips) {
        expect(chip.y).toBeLessThanOrEqual(chip.floorY + 1e-9);
      }
    }
  }
});

test('chips grow as they fall toward the viewer and never shrink on a bounce', () => {
  const frames = play(3);
  for (const [index, frame] of frames.entries()) {
    const before = frames[index - 1];
    if (before === undefined || frame.elapsedMs <= TOPPLE_END_MS) continue;
    for (const [chipIndex, chip] of frame.chips.entries()) {
      expect(chip.scale).toBeGreaterThanOrEqual(
        before.chips[chipIndex]?.scale ?? Number.NaN,
      );
    }
  }
  for (const chip of finalChips(frames)) {
    expect(chip.scale / chip.baseScale).toBeCloseTo(1.3, 9);
  }
});

test('each chip bounces lower than the time before', () => {
  for (const seed of SEEDS) {
    const frames = play(seed);
    for (let index = 0; index < restingChips().length; index += 1) {
      const peaks = bouncePeaks(frames, index);
      for (let bounce = 1; bounce < peaks.length; bounce += 1) {
        // Screen y grows downward, so a lower bounce peaks at a larger y.
        expect(peaks[bounce]).toBeGreaterThan(peaks[bounce - 1] ?? Number.NaN);
      }
    }
  }
});

test('some chips bounce more than once', () => {
  const bounces = finalChips(play(1)).map(chip => chip.bounces);

  expect(Math.max(...bounces)).toBeGreaterThanOrEqual(2);
});

test('settled chips lie flat on the floor, spread out, inside the stage', () => {
  for (const seed of SEEDS) {
    const chips = finalChips(play(seed));
    for (const chip of chips) {
      expect(chip.settled).toBe(true);
      expect(chip.y).toBe(chip.floorY);
      expect(Math.abs(chip.floorY - FLOOR_Y)).toBeLessThanOrEqual(FLOOR_SPREAD);
      expect(Math.abs(chip.flip % 180)).toBe(0);
      expect(chip.x).toBeGreaterThan(0);
      expect(chip.x).toBeLessThan(ART_WIDTH);
    }
    const xs = chips.map(chip => chip.x);
    expect(Math.max(...xs) - Math.min(...xs)).toBeGreaterThan(120);
  }
});

test('the same seed gives the same tumble, whatever the frame lengths', () => {
  expect(finalChips(play(4, 16))).toEqual(finalChips(play(4, 8)));
  expect(settledTumble(4).chips).toEqual(finalChips(play(4, 16)));
  expect(finalChips(play(4))).not.toEqual(finalChips(play(5)));
});

test('a long frame from a hidden tab advances the tumble by at most 50 ms', () => {
  const started = startTumble(idleTumble(), 1);

  expect(stepTumble(started, 10_000)).toEqual(stepTumble(started, 50));
});

test('a negative or non-finite frame time is rejected with the value in the message', () => {
  const started = startTumble(idleTumble(), 1);
  for (const dtMs of [-1, Number.NaN, Number.POSITIVE_INFINITY]) {
    expect(() => stepTumble(started, dtMs)).toThrow(
      new RangeError(
        `frame time ${String(dtMs)} ms must be a finite number at least 0`,
      ),
    );
  }
});

// The highest point (smallest y) a chip reaches after each bounce.
function bouncePeaks(frames: readonly Tumble[], index: number): number[] {
  const peaks: number[] = [];
  let bounces = 0;
  for (const frame of frames) {
    const chip = frame.chips[index];
    if (chip === undefined) continue;
    if (chip.bounces > bounces) {
      bounces = chip.bounces;
      peaks.push(chip.y);
    }
    if (bounces > 0 && chip.contact === 'air') {
      peaks[peaks.length - 1] = Math.min(peaks.at(-1) ?? chip.y, chip.y);
    }
  }
  return peaks.slice(0, -1);
}
