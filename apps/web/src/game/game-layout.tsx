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
import {createPortal} from 'react-dom';

import {Alert, AlertDescription} from '@/components/ui/alert';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';

import {useHeaderActions} from '../app/header-actions.ts';
import {CopyButton} from '../controls/copy-button.tsx';
import {useGame} from './game-context.ts';
import {GameplayPanel} from './gameplay-panel.tsx';

/** The game's page: the table, with the room code and Leave table in the header. */
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
