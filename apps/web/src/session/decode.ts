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

import * as z from 'zod';

import {
  Accounts,
  Catalogue,
  Error as ErrorBody,
  Frame,
  Health,
  Me,
  RoomView,
} from '../contract/contract.ts';
import {ContractError, TransportError} from './errors.ts';

/** The success bodies, by the name a route's caller expects. */
export interface Bodies {
  frame: Frame;
  catalogue: Catalogue;
  health: Health;
  me: Me;
  room: RoomView;
  accounts: Accounts;
}

// Compiled once: every response and every pushed frame takes the fast path.
const BODIES: {[K in keyof Bodies]: z.ZodType<Bodies[K]>} = {
  frame: z.compile(Frame),
  catalogue: z.compile(Catalogue),
  health: z.compile(Health),
  me: z.compile(Me),
  room: z.compile(RoomView),
  accounts: z.compile(Accounts),
};
const NAMES: Record<keyof Bodies, string> = {
  frame: 'Frame',
  catalogue: 'Catalogue',
  health: 'Health',
  me: 'Me',
  room: 'RoomView',
  accounts: 'Accounts',
};
const ERROR_BODY = z.compile(ErrorBody);

/**
 * The live position a stream event carries.
 *
 * @throws TransportError when the event is not a frame of the contract.
 */
export function decodeFrame(data: string): Frame {
  return parseBody(BODIES.frame, parseJson(data, 200), 200, NAMES.frame);
}

// The most of a body that is not JSON a message quotes, since it may be a
// whole error page.
const EXCERPT_LENGTH = 200;

/**
 * Decodes a response as the body `kind`.
 *
 * @throws ContractError when the server refused the request.
 * @throws TransportError when the response is not a body of the contract.
 */
export async function decode<K extends keyof Bodies>(
  response: Response,
  kind: K,
): Promise<Bodies[K]> {
  const status = String(response.status);
  let text: string;
  try {
    text = await response.text();
  } catch (e) {
    throw new TransportError(
      `The server's ${status} answer was cut off.`,
      response.status,
      {cause: e},
    );
  }
  if (!isJson(response)) {
    throw new TransportError(
      `The server answered ${status} without JSON: ${excerpt(text)}`,
      response.status,
    );
  }
  const body = parseJson(text, response.status);
  if (!response.ok) {
    const error = ERROR_BODY.safeParse(body);
    if (error.success) throw new ContractError(error.data, response.status);
    throw new TransportError(
      `The server answered ${status} without an error body: ${z.prettifyError(error.error)}`,
      response.status,
    );
  }
  return parseBody(BODIES[kind], body, response.status, NAMES[kind]);
}

function parseJson(text: string, status: number): unknown {
  try {
    return JSON.parse(text);
  } catch (e) {
    throw new TransportError('The server sent malformed JSON.', status, {
      cause: e,
    });
  }
}

function parseBody<T>(
  schema: z.ZodType<T>,
  body: unknown,
  status: number,
  kind: string,
): T {
  const parsed = schema.safeParse(body);
  if (parsed.success) return parsed.data;
  throw new TransportError(
    `The server answered ${String(status)} without a ${kind} body: ${z.prettifyError(parsed.error)}`,
    status,
  );
}

function isJson(response: Response): boolean {
  const type = response.headers.get('Content-Type') ?? '';
  return type.split(';')[0]?.trim().toLowerCase() === 'application/json';
}

function excerpt(text: string): string {
  const trimmed = text.trim();
  return trimmed.length <= EXCERPT_LENGTH
    ? trimmed
    : `${trimmed.slice(0, EXCERPT_LENGTH)}…`;
}
