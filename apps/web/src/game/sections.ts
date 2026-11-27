// Copyright 2026 DeepMind Technologies Limited
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

/** One tab of a panel group. */
export interface SectionDefinition {
  /** Unique within its group. */
  readonly id: string;
  /** The tab's label. */
  readonly title: string;
  /** What the section draws. */
  readonly Content: () => JSX.Element | null;
  /** The tab's label as it changes, "Legal (12)"; `title` when omitted. */
  readonly Label?: () => string;
  /** Whether the section has anything to show, and so a tab; always when omitted. */
  readonly Shown?: () => boolean;
  /** Drawn under the section while it is shown, such as History's replay control. */
  readonly Footer?: () => JSX.Element | null;
}

/** A tool panel: named sections, one shown at a time. */
export interface PanelGroupDefinition {
  readonly id: string;
  readonly title: string;
  readonly sections: readonly SectionDefinition[];
}
