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

import {type JSX, useState} from 'react';

import {Tabs, TabsContent, TabsList, TabsTrigger} from '@/components/ui/tabs';

import type {PanelGroupDefinition, SectionDefinition} from './sections.ts';

/** The properties of SectionTabs. */
export interface SectionTabsProps {
  readonly group: PanelGroupDefinition;
  /** The open section's id, when the caller keeps it. */
  readonly chosen?: string | undefined;
  readonly onChoose?: ((id: string) => void) | undefined;
}

/** A panel group's sections as tabs, one shown at a time. */
export function SectionTabs({
  group,
  chosen,
  onChoose,
}: SectionTabsProps): JSX.Element {
  const [own, setOwn] = useState<string | undefined>(undefined);
  const shown = group.sections.filter(section => section.Shown?.() ?? true);
  const open =
    [chosen, own].find(id => shown.some(section => section.id === id)) ??
    shown[0]?.id ??
    '';
  return (
    <Tabs
      value={open}
      onValueChange={id => {
        setOwn(id);
        onChoose?.(id);
      }}
    >
      <TabsList aria-label={`${group.title} sections`}>
        {shown.map(section => (
          <TabsTrigger key={section.id} value={section.id}>
            <SectionLabel section={section} />
          </TabsTrigger>
        ))}
      </TabsList>
      {shown.map(section => (
        <TabsContent key={section.id} value={section.id}>
          <section.Content />
          {section.Footer !== undefined && <section.Footer />}
        </TabsContent>
      ))}
    </Tabs>
  );
}

function SectionLabel({section}: {section: SectionDefinition}): string {
  return section.Label?.() ?? section.title;
}
