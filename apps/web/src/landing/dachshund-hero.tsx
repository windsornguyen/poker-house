import type {JSX, ReactNode} from 'react';

import {DachshundTable} from './dachshund-table.tsx';

import '../lobby.css';

/**
 * The dachshund, the name and the tagline, with `children` under them: the
 * lobby's table controls, or the landing page's sign-up.
 */
export function DachshundHero({
  children,
}: {
  readonly children: ReactNode;
}): JSX.Element {
  return (
    <>
      <div className="lobby__dachshund">
        <DachshundTable />
      </div>
      <div className="lobby__intro">
        <h1 id="lobby-title" className="lobby__title">
          doggybank
        </h1>
        <p className="lobby__tagline">
          Heads-up no-limit Texas Hold’em for Bots
        </p>
        {children}
      </div>
    </>
  );
}
