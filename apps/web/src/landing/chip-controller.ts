/**
 * Plays the chip tumble on the page: listens for the first disturbance, runs the
 * frames, and draws each chip with transforms only.
 *
 * Each chip element sits at its resting place by percentage `left` and `top`
 * (set once, so it scales with the drawing and shows before any script runs).
 * A frame moves it by a transform: the offset from rest in screen pixels, then
 * its tilt (rotateZ), its flip (rotateX, under the layer's perspective) and its
 * nearness (scale), about its own centre.
 */
import {ART_WIDTH, restingChips} from './chip-layout.ts';
import {
  type Tumble,
  TOPPLE_END_MS,
  idleTumble,
  settledTumble,
  startTumble,
  stepTumble,
} from './chip-tumble.ts';

/** Starts, rewinds and removes one dachshund's chip tumble. */
export type ChipController = Readonly<{
  trigger: () => void;
  resetChips: () => void;
  destroy: () => void;
}>;

/** The page parts a controller drives, and the window whose events disturb the chips. */
export type ChipStage = Readonly<{
  layer: HTMLElement;
  chips: readonly HTMLElement[];
  window: Window;
}>;

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';
// With reduced motion the chips fade out of the towers and into their resting places.
const FADE_MS = 220;
const FADING_ATTRIBUTE = 'data-fading';

/** Starts listening for the disturbance that topples the chips; call destroy() to stop. */
export function createChipController(stage: ChipStage): ChipController {
  const rests = restingChips();
  if (stage.chips.length !== rests.length) {
    throw new Error(
      `the drawing has ${String(stage.chips.length)} chip elements but ${String(rests.length)} resting chips; render one element per restingChips() entry`,
    );
  }
  const {window} = stage;
  let tumble: Tumble = idleTumble();
  let frame: number | null = null;
  let fade: number | null = null;
  let lastFrameMs: number | null = null;
  const draw = (): void => drawChips(stage, tumble);
  const tick = (nowMs: number): void => {
    tumble = stepTumble(tumble, lastFrameMs === null ? 0 : nowMs - lastFrameMs);
    lastFrameMs = nowMs;
    draw();
    frame =
      tumble.phase === 'SETTLED' ? null : window.requestAnimationFrame(tick);
  };
  const trigger = (): void => {
    if (tumble.phase !== 'IDLE') return;
    const seed = window.crypto.getRandomValues(new Uint32Array(1))[0] ?? 1;
    if (window.matchMedia(REDUCED_MOTION).matches) {
      tumble = settledTumble(seed);
      fadeTo(stage, draw, id => (fade = id));
      return;
    }
    tumble = startTumble(tumble, seed);
    lastFrameMs = null;
    frame = window.requestAnimationFrame(tick);
  };
  const cancel = (): void => {
    if (frame !== null) window.cancelAnimationFrame(frame);
    if (fade !== null) window.clearTimeout(fade);
    frame = null;
    fade = null;
  };
  const listeners = disturbanceListeners(
    window,
    trigger,
    downwardScrolls(window),
  );
  const resize = new ResizeObserver(draw);
  resize.observe(stage.layer);
  return {
    trigger,
    resetChips: () => {
      cancel();
      stage.layer.removeAttribute(FADING_ATTRIBUTE);
      tumble = idleTumble();
      draw();
    },
    destroy: () => {
      cancel();
      resize.disconnect();
      listeners();
    },
  };
}

// A click or tap, a key, or scrolling down (the page or any element in it) disturbs the chips. Every listener is
// passive and none prevents the default, so the page scrolls, types and clicks as usual.
function disturbanceListeners(
  window: Window,
  trigger: () => void,
  scrolledDown: (target: EventTarget) => boolean,
): () => void {
  const options = {capture: true, passive: true};
  const onWheel = (event: WheelEvent): void => {
    if (event.deltaY > 0) trigger();
  };
  const onScroll = (event: Event): void => {
    if (event.target !== null && scrolledDown(event.target)) trigger();
  };
  window.addEventListener('pointerdown', trigger, options);
  window.addEventListener('keydown', trigger, options);
  window.addEventListener('wheel', onWheel, options);
  window.addEventListener('scroll', onScroll, options);
  return () => {
    window.removeEventListener('pointerdown', trigger, options);
    window.removeEventListener('keydown', trigger, options);
    window.removeEventListener('wheel', onWheel, options);
    window.removeEventListener('scroll', onScroll, options);
  };
}

// The page scrolls the window; the lobby scrolls its own element. A capturing
// listener on the window hears both, and the target says which one moved.
function downwardScrolls(window: Window): (target: EventTarget) => boolean {
  const lastTops = new WeakMap<EventTarget, number>();
  return target => {
    const top = target instanceof Element ? target.scrollTop : window.scrollY;
    const down = top > (lastTops.get(target) ?? 0);
    lastTops.set(target, top);
    return down;
  };
}

function fadeTo(
  stage: ChipStage,
  draw: () => void,
  remember: (timeout: number) => void,
): void {
  stage.layer.setAttribute(FADING_ATTRIBUTE, '');
  remember(
    stage.window.setTimeout(() => {
      draw();
      stage.layer.removeAttribute(FADING_ATTRIBUTE);
    }, FADE_MS),
  );
}

// Until the chips leave the towers they keep their stacking order; after that
// a chip lower on the screen is nearer the viewer and drawn over the others.
function drawChips(stage: ChipStage, tumble: Tumble): void {
  const pixelsPerUnit = stage.layer.clientWidth / ART_WIDTH;
  const rests = restingChips();
  const byDepth = tumble.elapsedMs >= TOPPLE_END_MS;
  const order = tumble.chips
    .map((chip, index) => ({index, y: chip.y}))
    .sort((left, right) =>
      byDepth ? left.y - right.y : left.index - right.index,
    );
  for (const [rank, {index}] of order.entries()) {
    const element = stage.chips[index];
    const chip = tumble.chips[index];
    const rest = rests[index];
    if (element === undefined || chip === undefined || rest === undefined) {
      continue;
    }
    const dx = (chip.x - rest.x) * pixelsPerUnit;
    const dy = (chip.y - rest.y) * pixelsPerUnit;
    element.style.transform =
      `translate3d(${dx.toFixed(2)}px, ${dy.toFixed(2)}px, 0) ` +
      `rotateZ(${chip.rotZ.toFixed(2)}deg) rotateX(${chip.flip.toFixed(2)}deg) ` +
      `scale(${(chip.scale / chip.baseScale).toFixed(4)}) translate(-50%, -50%)`;
    const zIndex = String(rank + 1);
    if (element.style.zIndex !== zIndex) element.style.zIndex = zIndex;
  }
}
