// Copyright 2026 Doggybank contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import type {JSX} from 'react';

/** Renders the decorative dachshund coin-bank mark, sized by CSS. */
export function LogoMark({
  className,
}: {
  readonly className?: string;
}): JSX.Element {
  return (
    <svg
      className={className}
      viewBox="0 0 128 128"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="var(--logo-chip)"
        d="M32.38 65.5A24.5 24.5 0 1 1 65.62 65.5Z"
      />
      <path
        fill="var(--logo-chip-inlay)"
        d="M28.69 40.76A22.2 22.2 0 0 1 32.04 33.19L35.71 36.28A17.4 17.4 0 0 0 33.08 42.22Z"
      />
      <path
        fill="var(--logo-chip-inlay)"
        d="M44.59 25.74A22.2 22.2 0 0 1 53.41 25.74L52.46 30.45A17.4 17.4 0 0 0 45.54 30.45Z"
      />
      <path
        fill="var(--logo-chip-inlay)"
        d="M65.96 33.19A22.2 22.2 0 0 1 69.31 40.76L64.92 42.22A17.4 17.4 0 0 0 62.29 36.28Z"
      />
      <circle cx="49" cy="47.5" r="14.8" fill="var(--logo-chip-ring)" />
      <circle cx="49" cy="47.5" r="10" fill="var(--logo-chip)" />
      <path
        fill="var(--logo-chip-inlay)"
        d="M49 42L54.5 47.5L49 53L43.5 47.5Z"
      />
      <path
        fill="var(--logo-coat)"
        d="M16 73.5C8 67.5 3.8 56 6.2 44.5A5 5 0 0 1 16 46.2C14.6 54.5 17.5 62 24 66.5Z"
      />
      <path
        fill="var(--logo-coat)"
        fillRule="evenodd"
        d="M22.5 62.5Q25.2 62.5 25.2 65.2V67.5Q25.2 70 27.7 70H70.3Q72.8 70 72.8 67.5V65.2Q72.8 62.5 75.5 62.5Q77.8 62.5 78.2 59.8L79.6 45.5A18.2 18.2 0 0 1 113 38.5C115 41.4 117.5 42.6 121.2 43A6.4 6.4 0 0 1 125.5 49.5C125.5 54.5 121.5 57.5 115.5 57.5H108.2Q105.5 57.5 104.8 60.2L101.2 78.5A14 14 0 0 1 94.5 90.8V100.5A7 7 0 0 1 80.5 100.5V92.5H36V100.5A7 7 0 0 1 22 100.5V90.5A14 14 0 0 1 11.5 77A14.5 14.5 0 0 1 22.5 62.5ZM86.2 44.2A9.4 9.4 0 0 1 104.8 46.8L101.6 61.2A9.4 9.4 0 0 1 83 58.6Z"
      />
      <path
        fill="var(--logo-collar)"
        d="M78 64L103.2 68.4L101.9 74.8L76.8 70.4Z"
      />
      <path
        fill="var(--logo-ear)"
        d="M88.8 44.8A6.8 6.8 0 0 1 102.2 46.7L99.2 60A6.8 6.8 0 0 1 85.8 58.1Z"
      />
      <circle cx="107.5" cy="37.8" r="2.1" fill="var(--logo-brow)" />
      <circle cx="109.5" cy="43" r="2.7" fill="var(--logo-eye)" />
      <circle cx="122.5" cy="46.8" r="3.8" fill="var(--logo-nose)" />
    </svg>
  );
}
