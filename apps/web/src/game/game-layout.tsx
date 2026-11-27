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

import {PanelRightIcon} from 'lucide-react';
import {type JSX, useState} from 'react';
import {createPortal} from 'react-dom';

import {Alert, AlertDescription} from '@/components/ui/alert';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import {Tabs, TabsContent, TabsList, TabsTrigger} from '@/components/ui/tabs';

import {useHeaderActions} from '../app/header-actions.ts';
import {BotOutputView} from '../bot-output/bot-output.tsx';
import {CopyButton} from '../controls/copy-button.tsx';
import {SETUP_GROUP, SetupPanel} from '../setup/setup-panel.tsx';
import {STATE_GROUP} from '../state/state-panel.tsx';
import {VIEW_GROUP} from '../view/view-panel.tsx';
import {ACTIONS_GROUP} from './actions-panel.tsx';
import {useGame} from './game-context.ts';
import {GameplayPanel} from './gameplay-panel.tsx';
import {SectionTabs} from './section-tabs.tsx';
import {SESSION_GROUP} from './session-panel.tsx';

interface Tool {
  readonly id: string;
  readonly title: string;
  readonly Content: () => JSX.Element;
}

const TOOLS: readonly Tool[] = [
  {
    id: ACTIONS_GROUP.id,
    title: ACTIONS_GROUP.title,
    Content: () => <SectionTabs group={ACTIONS_GROUP} />,
  },
  {id: 'bot_output', title: 'Bot output', Content: BotOutput},
  {id: SETUP_GROUP.id, title: SETUP_GROUP.title, Content: SetupPanel},
  {
    id: VIEW_GROUP.id,
    title: VIEW_GROUP.title,
    Content: () => <SectionTabs group={VIEW_GROUP} />,
  },
  {
    id: STATE_GROUP.id,
    title: STATE_GROUP.title,
    Content: () => <SectionTabs group={STATE_GROUP} />,
  },
  {
    id: SESSION_GROUP.id,
    title: SESSION_GROUP.title,
    Content: () => <SectionTabs group={SESSION_GROUP} />,
  },
];

/** The game's page: the table, and the tool panels in a sheet. */
export function GameLayout(): JSX.Element {
  const {error, frame} = useGame().session;
  const header = useHeaderActions();
  const [refusal, setRefusal] = useState<string | null>(null);
  const code = frame?.session.code;
  return (
    <div className="flex flex-col gap-3 p-3">
      {error !== null && (
        <Alert variant="destructive">
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}
      {refusal !== null && (
        <Alert variant="destructive">
          <AlertDescription>{refusal}</AlertDescription>
        </Alert>
      )}
      <GameplayPanel />
      {header !== null &&
        createPortal(
          <>
            {code !== undefined && <RoomCode code={code} />}
            {frame?.session.staked === true && (
              <LeaveTable onRefused={setRefusal} />
            )}
            <ToolSheet />
          </>,
          header,
        )}
    </div>
  );
}

// Cashes out between hands. While a hand is played the server refuses, and
// says why.
function LeaveTable({
  onRefused,
}: {
  readonly onRefused: (message: string) => void;
}): JSX.Element {
  const {leave} = useGame();
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => {
        leave().catch((caught: unknown) => {
          onRefused(caught instanceof Error ? caught.message : String(caught));
        });
      }}
    >
      Leave table
    </Button>
  );
}

function ToolSheet(): JSX.Element {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Panels">
          <PanelRightIcon />
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <div className="sr-only">
          <SheetHeader>
            <SheetTitle>Panels</SheetTitle>
          </SheetHeader>
        </div>
        <div className="flex min-h-0 flex-1 flex-col p-4 pr-12">
          <Tabs defaultValue={ACTIONS_GROUP.id} className="min-h-0 flex-1">
            <TabsList className="h-auto flex-wrap">
              {TOOLS.map(tool => (
                <TabsTrigger key={tool.id} value={tool.id}>
                  {tool.title}
                </TabsTrigger>
              ))}
            </TabsList>
            {TOOLS.map(tool => (
              <TabsContent
                key={tool.id}
                value={tool.id}
                className="min-h-0 overflow-auto"
              >
                <tool.Content />
              </TabsContent>
            ))}
          </Tabs>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function RoomCode({code}: {code: string}): JSX.Element {
  return (
    <div className="flex items-center gap-1">
      <Badge variant="outline" aria-label="Room code">
        {code}
      </Badge>
      <CopyButton text={code} />
    </div>
  );
}

function BotOutput(): JSX.Element {
  return <BotOutputView frame={useGame().session.frame} />;
}
