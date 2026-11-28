// Mounts the tea corner on a docs page and plays one pour each time the reader scrolls.
import {PART_IDS, type PartId, renderTeaScene} from './drawing.ts';
import {
  type Motion,
  type Playback,
  SEQUENCE_MS,
  type TeaFrame,
  afterScrollIntent,
  afterTick,
  teaFrame,
} from './timeline.ts';

const CONTAINER_ID = 'tea-corner';
const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';
/** The shoulder the reaching arm turns around, in the ghost's local coordinates. */
const SHOULDER = '-10.4 -11.6';
/** How far the arm turns up toward the cup when fully raised, in degrees counterclockwise. */
const ARM_RAISE_DEG = 40;
/** How far the steam drifts up over its whole rise, in view-box units. */
const STEAM_RISE = 4;
/** The tea surface at an empty and a full cup: centre height below the rim and half-width. */
const SURFACE_EMPTY = {drop: 2.4, halfWidth: 2.5};
const SURFACE_FULL = {drop: 0, halfWidth: 3.9};
/** Below this level the surface is hidden, so an empty cup shows no tea. */
const VISIBLE_LEVEL = 0.01;

type Parts = Readonly<Record<PartId, SVGElement>>;

/** Adds the tea corner to the page once; later calls do nothing. */
export function mountTeaCorner(document: Document, window: Window): void {
  if (document.getElementById(CONTAINER_ID) !== null) {
    return;
  }
  const container = document.createElement('div');
  container.id = CONTAINER_ID;
  container.className = 'tea-corner';
  container.setAttribute('aria-hidden', 'true');
  container.innerHTML = renderTeaScene();
  const parts = requireParts(container);
  document.body.append(container);
  showFrame(parts, teaFrame(0));
  startPlayer(parts, window);
}

function requireParts(container: HTMLElement): Parts {
  const found: Partial<Record<PartId, SVGElement>> = {};
  for (const id of PART_IDS) {
    const element = container.querySelector(`#${id}`);
    if (!(element instanceof SVGElement)) {
      throw new Error(
        `tea corner part \`${id}\` is missing from the drawing; add it to drawing.ts`,
      );
    }
    found[id] = element;
  }
  return found as Parts; // Every id in PART_IDS was assigned above.
}

function startPlayer(parts: Parts, window: Window): void {
  const motionQuery = window.matchMedia(REDUCED_MOTION);
  let playback: Playback = {kind: 'idle'};
  const motion = (): Motion => (motionQuery.matches ? 'reduced' : 'full');
  const tick = (frameMs: number): void => {
    playback = afterTick(playback, frameMs);
    if (playback.kind !== 'playing') {
      showFrame(parts, teaFrame(SEQUENCE_MS));
      return;
    }
    showFrame(parts, teaFrame(frameMs - playback.startedAtMs));
    window.requestAnimationFrame(tick);
  };
  const onScrollIntent = (): void => {
    const before = playback;
    playback = afterScrollIntent(playback, motion());
    if (before.kind === 'idle' && playback.kind === 'starting') {
      window.requestAnimationFrame(tick);
    }
  };
  // A wheel or a swipe counts even on a page too short to scroll.
  const passive = {passive: true, capture: true};
  window.addEventListener('scroll', onScrollIntent, passive);
  window.addEventListener('wheel', onScrollIntent, passive);
  window.addEventListener('touchmove', onScrollIntent, passive);
}

function showFrame(parts: Parts, frame: TeaFrame): void {
  pose(parts['tea-pitcher'], frame.pitcher);
  pose(parts['tea-cup'], frame.cup);
  showTea(parts['tea-surface'], frame.teaLevel);
  showStream(parts['tea-stream'], frame.stream);
  parts['tea-steam'].setAttribute('opacity', fixed(frame.steam.opacity));
  parts['tea-steam'].setAttribute(
    'transform',
    `translate(0 ${fixed(-STEAM_RISE * frame.steam.rise)})`,
  );
  parts['tea-ghost'].setAttribute(
    'transform',
    `translate(${fixed(frame.ghost.x)} ${fixed(frame.ghost.y)})`,
  );
  parts['tea-ghost-arm'].setAttribute(
    'transform',
    `rotate(${fixed(-ARM_RAISE_DEG * frame.ghostArmRaise)} ${SHOULDER})`,
  );
  const closed = frame.ghostEyes === 'closed';
  parts['tea-eyes-open'].setAttribute(
    'visibility',
    closed ? 'hidden' : 'visible',
  );
  parts['tea-eyes-closed'].setAttribute(
    'visibility',
    closed ? 'visible' : 'hidden',
  );
}

function pose(element: SVGElement, placement: TeaFrame['cup']): void {
  element.setAttribute(
    'transform',
    `translate(${fixed(placement.x)} ${fixed(placement.y)}) rotate(${fixed(placement.angleDeg)})`,
  );
}

// The surface sinks into the narrowing bowl as the level falls, so it also gets narrower.
function showTea(surface: SVGElement, level: number): void {
  const drop =
    SURFACE_EMPTY.drop + (SURFACE_FULL.drop - SURFACE_EMPTY.drop) * level;
  const halfWidth =
    SURFACE_EMPTY.halfWidth +
    (SURFACE_FULL.halfWidth - SURFACE_EMPTY.halfWidth) * level;
  surface.setAttribute('cy', fixed(-4.6 + drop));
  surface.setAttribute('rx', fixed(halfWidth));
  surface.setAttribute(
    'visibility',
    level > VISIBLE_LEVEL ? 'visible' : 'hidden',
  );
}

// A falling stream is a parabola leaving the spout level: the quadratic Bézier from start
// to end whose control point is ((start.x + end.x) / 2, start.y). With pathLength 1, the
// dash from `tail` to `head` is the part of the stream in the air.
function showStream(stream: SVGElement, value: TeaFrame['stream']): void {
  const length = value.head - value.tail;
  const {start, end} = value;
  stream.setAttribute(
    'd',
    `M${fixed(start.x)} ${fixed(start.y)}Q${fixed((start.x + end.x) / 2)} ${fixed(start.y)} ${fixed(end.x)} ${fixed(end.y)}`,
  );
  stream.setAttribute('stroke-dasharray', `${fixed(length)} 2`);
  stream.setAttribute('stroke-dashoffset', fixed(-value.tail));
  stream.setAttribute('visibility', length > 0 ? 'visible' : 'hidden');
}

function fixed(value: number): string {
  return value.toFixed(3);
}

mountTeaCorner(document, window);
