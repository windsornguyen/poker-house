import {
  type JSX,
  type Ref,
  useEffect,
  useImperativeHandle,
  useRef,
} from 'react';

import {
  ART_WIDTH,
  CHIP_WIDTH,
  STAGE_HEIGHT,
  restingChips,
} from './chip-layout.ts';
import {type ChipController, createChipController} from './chip-controller.ts';
import './dachshund-table.css';

/** Replays the tumble from the start: the chips go back onto the dog's back. */
export type DachshundTableHandle = Readonly<{resetChips: () => void}>;

const DOG_SRC = '/landing/dachshund.webp';
const DOG_WIDTH_PX = 1600;
const DOG_HEIGHT_PX = 534;
// Two hand-drawn variants, so neighbouring chips do not look stamped.
const CHIP_SRCS = ['/landing/chip-a.svg', '/landing/chip-b.svg'] as const;
const RESTS = restingChips();

/**
 * The long dachshund whose back is a poker table. The first click, key press or
 * scroll down knocks its two red chip towers onto an invisible floor below it.
 */
export function DachshundTable({
  ref,
}: {
  ref?: Ref<DachshundTableHandle>;
}): JSX.Element {
  const layer = useRef<HTMLDivElement>(null);
  const chips = useRef<Array<HTMLImageElement | null>>([]);
  const controller = useRef<ChipController | null>(null);
  useImperativeHandle(ref, () => ({
    resetChips: () => controller.current?.resetChips(),
  }));
  useEffect(() => {
    const element = layer.current;
    const elements = chips.current.filter(chip => chip !== null);
    if (element === null) return undefined;
    const created = createChipController({
      layer: element,
      chips: elements,
      window,
    });
    controller.current = created;
    return () => {
      created.destroy();
      controller.current = null;
    };
  }, []);
  return (
    <figure
      className="dachshund"
      style={{aspectRatio: `${String(ART_WIDTH)} / ${String(STAGE_HEIGHT)}`}}
    >
      <img
        className="dachshund__dog"
        src={DOG_SRC}
        width={DOG_WIDTH_PX}
        height={DOG_HEIGHT_PX}
        alt="A very long dachshund carrying poker chips on its back"
        draggable={false}
      />
      <div className="dachshund__chips" ref={layer} aria-hidden="true">
        {RESTS.map((rest, index) => (
          <img
            key={`${rest.tower.name}-${String(rest.level)}`}
            ref={element => {
              chips.current[index] = element;
            }}
            className="dachshund__chip"
            src={CHIP_SRCS[index % CHIP_SRCS.length]}
            alt=""
            draggable={false}
            style={{
              left: percent(rest.x, ART_WIDTH),
              top: percent(rest.y, STAGE_HEIGHT),
              width: percent(CHIP_WIDTH * rest.tower.scale, ART_WIDTH),
              zIndex: index + 1,
            }}
          />
        ))}
      </div>
    </figure>
  );
}

function percent(part: number, whole: number): string {
  return `${((100 * part) / whole).toFixed(4)}%`;
}
