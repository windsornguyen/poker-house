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

// Generated from apps/server/src/poker_house_server/contract.schema.json by
// scripts/generate_contract.ts. Do not edit; run pnpm generate:contract.

/**
 * Every response body the server sends.
 */
export type ResponseBody = Frame | Catalogue | Health | SessionClosed | Error;

/**
 * A legal action at a position.
 *
 * Attributes:
 *   id: The OpenSpiel action id, which a client sends to play it.
 *   label: The game's text for the action.
 */
export interface Action {
  id: number;
  label: string;
}

/**
 * What a game's adapter says about one legal action, for its renderer.
 *
 * Attributes:
 *   id: The legal action's OpenSpiel id.
 *   hint: The adapter's description of the action, such as the card it plays
 *     or the cells it joins.
 */
export interface ActionHint {
  id: number;
  hint: JsonValue;
}

/**
 * Lets controllers play their seats.
 *
 * Play stops when a human seat or an exposed chance node must act, the game
 * ends, a controller fails, or `max_plies` seat actions have been applied.
 * Under the `auto` policy, chance outcomes are sampled as they come and do
 * not count.
 *
 * One request holds its session until play stops, so play is bounded.
 *
 * Attributes:
 *   max_plies: The most seat actions to apply, from 1 to 1000, or null for
 *     1000.
 */
export interface Advance {
  max_plies: number | null;
}

/**
 * Plays an action for the seat to move.
 *
 * Attributes:
 *   action: The OpenSpiel action id, one of the frame's `legal_actions`.
 *   ply: The position to play at, the `ply` of the frame the action was
 *     chosen from: null, or `num_plies`, for the live position. An earlier
 *     ply plays from that position and takes back every later ply, as only
 *     an omniscient viewer may.
 */
export interface ApplyAction {
  action: number;
  ply: number | null;
}

/**
 * Chooses the outcome at a chance node under the `expose` policy.
 *
 * Attributes:
 *   outcome: The OpenSpiel action id, one of the frame's `chance_outcomes`.
 *   ply: The position to choose at, as for `ApplyAction`.
 */
export interface ApplyChanceOutcome {
  outcome: number;
  ply: number | null;
}

/**
 * What a bot said about one of its choices, beyond the action.
 *
 * Attributes:
 *   policy: The bot's probabilities over the legal actions where it chose,
 *     most probable first, each action at most once; empty when it gave
 *     none. Their sum is at most 1, as a bot may give only its likeliest
 *     actions. Either every entry has its action or none does.
 *   value: The bot's estimate of the position's value for its seat, or null
 *     when it gave none.
 *   decided_by: What part of the bot made the choice, such as `network`,
 *     `search`, `scripted` or `forced`; null when it did not say.
 */
export interface BotOutput {
  policy: PolicyEntry[];
  value: number | null;
  decided_by: string | null;
}

/**
 * What the server can do, independent of any one game.
 *
 * Attributes:
 *   controllers: Every registered controller, starting with the human one.
 *   chance_policies: The chance policies the server accepts.
 */
export interface Capabilities {
  controllers: Controller[];
  chance_policies: ChancePolicy[];
}

/**
 * Every game the server knows.
 *
 * Attributes:
 *   games: One entry per game, ordered by name.
 */
export interface Catalogue {
  games: CatalogueEntry[];
}

/**
 * A game the server knows, and whether it can serve it.
 *
 * Attributes:
 *   name: The game's short name, which a client sends to create a session.
 *   long_name: The game's display name.
 *   dynamics: How players move.
 *   chance_mode: How the game uses chance.
 *   information: What the players observe.
 *   min_seats: The fewest seats the game supports.
 *   max_seats: The most seats the game supports.
 *   num_players: The number of seats the game has with its default
 *     parameters, between `min_seats` and `max_seats`; null when not
 *     loadable.
 *   parameters: The game's parameters, ordered by name.
 *   loadable: Whether the server can serve the game.
 *   unavailable_reason: Why the server cannot serve the game; null when
 *     loadable.
 *   controllers: The `Controller.name`s that can play the game with its
 *     default parameters; empty when not loadable.
 *   renderer: The renderer its frames name in `Presentation.renderer`, from
 *     the game's registered adapter: the board a client draws it with, if
 *     the client has that renderer. Null for a game with no adapter, and for
 *     one that is not loadable; such a game is shown as its text.
 */
export interface CatalogueEntry {
  name: string;
  long_name: string;
  dynamics: Dynamics;
  chance_mode: ChanceMode;
  information: Information;
  min_seats: number;
  max_seats: number;
  num_players: number | null;
  parameters: ParameterSpec[];
  loadable: boolean;
  unavailable_reason: string | null;
  controllers: string[];
  renderer: string | null;
}

/**
 * How the game uses chance, as the game declares it.
 *
 * Attributes:
 *   DETERMINISTIC: The game has no chance nodes.
 *   EXPLICIT_STOCHASTIC: Chance nodes list their outcomes and probabilities.
 *   SAMPLED_STOCHASTIC: Chance outcomes are sampled inside the state.
 */
export type ChanceMode =
  | 'deterministic'
  | 'explicit_stochastic'
  | 'sampled_stochastic';

/**
 * A chance outcome at a chance node.
 *
 * Attributes:
 *   id: The OpenSpiel action id, which a client sends to choose it.
 *   label: The game's text for the outcome.
 *   probability: The outcome's probability, in (0, 1].
 */
export interface ChanceOutcome {
  id: number;
  label: string;
  probability: number;
}

/**
 * How chance nodes are resolved.
 *
 * Attributes:
 *   AUTO: The server samples each outcome from a seeded generator.
 *   EXPOSE: The client chooses each outcome; in a game that hides
 *     information, only from the oracle view.
 */
export type ChancePolicy = 'auto' | 'expose';

/**
 * A kind of agent that can play a seat.
 *
 * Attributes:
 *   name: The stable identifier used in requests and in `SeatView.controller`.
 *   label: The human-readable name.
 *   config_schema: A JSON Schema object that a seat's `config` for this
 *     controller must satisfy; `{}` when it takes no settings. Each of its
 *     `properties` gives a setting's `type`, `default` and constraints; a
 *     setting listed in its `required` has no `default`, and a seat must be
 *     given it.
 *   unavailable_reason: Why the controller cannot play the session's game;
 *     null when it can. A seat is never played by a controller with a
 *     reason.
 */
export interface Controller {
  name: string;
  label: string;
  config_schema: Record<string, JsonValue>;
  unavailable_reason: string | null;
}

/**
 * Why a seat's controller stopped playing.
 *
 * Attributes:
 *   error: The name of the exception the controller raised.
 *   message: The exception's message; null for every viewer that is not
 *     omniscient, the failing seat included, since the message may describe
 *     any seat's private state.
 */
export interface ControllerFailure {
  error: string;
  message: string | null;
}

/**
 * Starts a session.
 *
 * Attributes:
 *   game: The game's short name.
 *   parameters: Game parameters; omitted ones take their defaults.
 *   seats: Who plays each seat, in seat order, one per seat of the game.
 *   chance_policy: How chance nodes are resolved.
 *   seed: The chance generator's seed, a non-negative integer, or null for
 *     the server to choose one.
 */
export interface CreateSession {
  game: string;
  parameters: Record<string, boolean | number | string>;
  seats: SeatConfig[];
  chance_policy: ChancePolicy;
  seed: number | null;
}

/**
 * How players move, as the game declares it.
 *
 * Attributes:
 *   SEQUENTIAL: One player acts at a time.
 *   SIMULTANEOUS: Players act together; served through the turn-based wrapper.
 *   MEAN_FIELD: A mean-field game.
 */
export type Dynamics = 'sequential' | 'simultaneous' | 'mean_field';

/**
 * A refused request.
 *
 * Attributes:
 *   code: Why the request was refused.
 *   message: A human-readable explanation, safe to show the requester: it
 *     never holds state the requester may not see.
 *   seat: The seat the refusal concerns, or null.
 *   ply: The index of the history entry the refusal concerns, or null.
 */
export interface Error {
  code: ErrorCode;
  message: string;
  seat: number | null;
  ply: number | null;
}

/**
 * Why a request was refused.
 *
 * Attributes:
 *   BAD_REQUEST: The request is malformed.
 *   NOT_FOUND: The session, game, seat or ply does not exist.
 *   METHOD_NOT_ALLOWED: The path exists but does not accept the method.
 *   GAME_UNAVAILABLE: The game cannot be served; its catalogue entry says why.
 *   VIEWER_UNAVAILABLE: The game cannot build a frame for the viewer.
 *   NOT_YOUR_TURN: The viewer may not choose the next action.
 *   ILLEGAL_ACTION: The action is not legal at the position.
 *   CONTROLLER_UNAVAILABLE: The controller cannot play the game, or its
 *     settings do not satisfy its `config_schema`.
 *   CONTROLLER_FAILED: A seat's controller failed and the session is paused.
 *   NOTHING_TO_UNDO: The live game has no action to undo.
 */
export type ErrorCode =
  | 'bad_request'
  | 'not_found'
  | 'method_not_allowed'
  | 'game_unavailable'
  | 'viewer_unavailable'
  | 'not_your_turn'
  | 'illegal_action'
  | 'controller_unavailable'
  | 'controller_failed'
  | 'nothing_to_undo';

/**
 * A position of a session, built for one viewer.
 *
 * A frame is live when `ply == num_plies`, and a replay of an earlier position
 * otherwise. A seat acts at the live position; an omniscient viewer may also
 * play from a replay, which takes back the plies after it.
 *
 * Attributes:
 *   session: The session's fixed properties.
 *   viewer: The audience the frame is built for.
 *   omniscient: Whether the viewer sees the full state: exactly when the
 *     viewer is the oracle or the game hides nothing
 *     (`session.hides_information` is false).
 *   status: The state of the session's live game.
 *   seats: Every seat, in seat order.
 *   ply: The number of actions, chance outcomes included, applied to reach
 *     this position.
 *   num_plies: The number of actions in the live game.
 *   to_move: Who acts at this position.
 *   legal_actions: The actions the acting seat may choose; empty where no
 *     seat acts and, for a viewer that is not omniscient, on a replay; null
 *     when withheld from the viewer.
 *   chance_outcomes: The outcomes the client may choose at a chance node under
 *     the `expose` policy; empty otherwise, null when withheld from the viewer.
 *   history: Every action of the live game, in order, as the viewer may see
 *     it.
 *   rewards: Each seat's reward for the action that reached this position, in
 *     seat order; null at the initial position or when that action is
 *     withheld from the viewer.
 *   returns: Each seat's return, in seat order, at a terminal position;
 *     otherwise null.
 *   state_text: The full state as text; null unless `omniscient`.
 *   observation_text: The viewer's observation as text; null unless the viewer
 *     holds a seat and the game provides observations.
 *   information_state_text: The viewer's information state as text; null
 *     unless the viewer holds a seat and the game provides information states.
 *   struct: The full state as the game's structured JSON; null unless
 *     `omniscient` and the game provides it.
 *   observation_struct: The viewer's observation as the game's structured
 *     JSON; null unless the viewer holds a seat and the game provides
 *     observation structs.
 *   presentation: The position as the game's adapter presents it to the
 *     viewer; null when no adapter is registered for the game.
 */
export interface Frame {
  session: SessionInfo;
  viewer: Viewer;
  omniscient: boolean;
  status: SessionStatus;
  seats: SeatView[];
  ply: number;
  num_plies: number;
  to_move: ToMove;
  legal_actions: Action[] | null;
  chance_outcomes: ChanceOutcome[] | null;
  history: HistoryEntry[];
  rewards: number[] | null;
  returns: number[] | null;
  state_text: string | null;
  observation_text: string | null;
  information_state_text: string | null;
  struct: JsonValue;
  observation_struct: JsonValue;
  presentation: Presentation | null;
}

/**
 * The server's identity and capabilities.
 *
 * Attributes:
 *   version: The installed Poker House server package's version.
 *   revision: The source revision the server runs from, or null when unknown.
 *   capabilities: What the server can do.
 */
export interface Health {
  version: string;
  revision: string | null;
  capabilities: Capabilities;
}

/**
 * One action of the live game, as the viewer may see it.
 *
 * Attributes:
 *   seat: The seat that acted, or null for a chance outcome.
 *   action: The OpenSpiel action id, or null when withheld from the viewer.
 *   label: The game's text for the action, or null when withheld.
 *   rewards: Each seat's reward for the action, in seat order, or null when
 *     withheld.
 *   public_label: What every viewer may read of a withheld action, as the
 *     game's adapter says, such as a card discarded face up; null when the
 *     action is shown in full or wholly hidden.
 *   bot_output: What the seat's controller said about the action: its
 *     policy, value and what decided it. It goes with the action in full: to
 *     an omniscient viewer and to the seat's own, and null for any other
 *     viewer, since in a game that hides information a bot's policy, value
 *     and what decided its move all follow from its hand. Null also when the
 *     controller said nothing.
 */
export interface HistoryEntry {
  seat: number | null;
  action: number | null;
  label: string | null;
  rewards: number[] | null;
  public_label: string | null;
  bot_output: BotOutput | null;
}

/**
 * What the players observe, as the game declares it.
 *
 * Attributes:
 *   ONE_SHOT: A one-shot game.
 *   PERFECT_INFORMATION: Every player observes the full state.
 *   IMPERFECT_INFORMATION: Some state is hidden from some players.
 */
export type Information =
  | 'one_shot'
  | 'perfect_information'
  | 'imperfect_information';

/**
 * Any JSON value.
 */
export type JsonValue = unknown;

/**
 * Who acts at a position.
 *
 * Attributes:
 *   SEAT: A seat chooses the next action.
 *   CHANCE: Chance chooses the next action.
 *   TERMINAL: The game is over and nobody acts.
 */
export type MoverKind = 'seat' | 'chance' | 'terminal';

/**
 * Which values a game parameter admits.
 *
 * Attributes:
 *   FREE: Any value of its type.
 *   RANGE: A number between `minimum` and `maximum`, inclusive.
 *   CHOICE: One of `choices`.
 */
export type ParameterKind = 'free' | 'range' | 'choice';

/**
 * A game parameter, as a client needs it to offer the parameter.
 *
 * Attributes:
 *   name: The parameter's name, a key of a session's `parameters`.
 *   type: The type of the parameter's value.
 *   kind: Which values the parameter admits.
 *   default: The value the game uses when none is given.
 *   minimum: The least admitted value when `kind` is `range`, otherwise null.
 *   maximum: The greatest admitted value when `kind` is `range`, otherwise
 *     null.
 *   choices: The admitted values when `kind` is `choice`, otherwise null.
 *   description: What the parameter controls, or null when the game does not
 *     say.
 */
export interface ParameterSpec {
  name: string;
  type: ParameterType;
  kind: ParameterKind;
  default: boolean | number | string;
  minimum: number | null;
  maximum: number | null;
  choices: Array<boolean | number | string> | null;
  description: string | null;
}

/**
 * The type of a game parameter's value.
 *
 * Attributes:
 *   BOOL: A boolean.
 *   INT: An integer.
 *   FLOAT: A real number.
 *   STRING: A string.
 */
export type ParameterType = 'bool' | 'int' | 'float' | 'string';

/**
 * One action of a bot's policy, with the probability it gave it.
 *
 * Attributes:
 *   action: The OpenSpiel action id, a legal action where the bot chose.
 *     The schema's type admits null, but a history entry carries a bot
 *     output only when its own action is given, and then every policy
 *     entry's action is given too, so no frame holds a null one.
 *   label: The game's text for the action.
 *   prob: The probability the bot gave the action, in [0, 1].
 */
export interface PolicyEntry {
  action: number | null;
  label: string;
  prob: number;
}

/**
 * A position as the game's adapter presents it to one viewer.
 *
 * Attributes:
 *   renderer: The name of the client renderer that draws the view.
 *   view: The adapter's view of the position, holding only what the viewer
 *     may see.
 *   actions: The adapter's hints for the legal actions, each naming an action
 *     of the frame's `legal_actions` at most once; null exactly when the
 *     frame's `legal_actions` is null.
 */
export interface Presentation {
  renderer: string;
  view: JsonValue;
  actions: ActionHint[] | null;
}

/**
 * Restarts the live game, keeping the session's seats.
 *
 * Attributes:
 *   history: Actions to replay from the initial state, chance outcomes
 *     included, as in a frame's `history`; null or empty for a fresh game.
 */
export interface Reset {
  history: number[] | null;
}

/**
 * Who plays a seat.
 *
 * Attributes:
 *   controller: The `Controller.name` to play the seat.
 *   config: The controller's settings, satisfying its `config_schema`.
 *   autoplay: Whether the server plays the seat's moves as soon as it is to
 *     move. Must be false for a human seat.
 */
export interface SeatConfig {
  controller: string;
  config: Record<string, boolean | number | string>;
  autoplay: boolean;
}

/**
 * Whether a seat's controller is ready to play.
 *
 * Attributes:
 *   READY: The controller is built and plays the seat; a human seat is always
 *     ready.
 *   PREPARING: The server is building the controller, which can take a while
 *     (a trained model loads and warms up). The seat does not move until it
 *     is ready; then autoplay goes on.
 *   UNAVAILABLE: The controller could not be built, or was not built within
 *     the build budget. The seat has a `failure`, so the session is paused
 *     until the seat is given a controller again.
 */
export type SeatStatus = 'ready' | 'preparing' | 'unavailable';

/**
 * One seat of a session.
 *
 * Attributes:
 *   seat: The seat index, which is the OpenSpiel player id.
 *   controller: The `Controller.name` playing the seat.
 *   config: The controller's settings, satisfying its `config_schema`.
 *     Every viewer receives them, so they hold no secret.
 *   autoplay: Whether the server plays the seat's moves as soon as it is to
 *     move, rather than on an advance request. Never true for a human seat.
 *   failure: Why the controller failed, or null while it plays.
 *   status: Whether the controller is ready, being built, or could not be
 *     built.
 *   message: Why the seat is not ready, for every viewer: what the server is
 *     doing while it is `preparing`, or why it is `unavailable`; null when it
 *     is `ready`, and optional while it is `preparing`.
 *   notice: The controller's short note about its latest choice, such as a
 *     remote bot reporting something it recovered from; null when it gave
 *     none. Only the seat's own viewer and omniscient viewers receive it. It
 *     has no effect on play.
 */
export interface SeatView {
  seat: number;
  controller: string;
  config: Record<string, boolean | number | string>;
  autoplay: boolean;
  failure: ControllerFailure | null;
  status: SeatStatus;
  message: string | null;
  notice: string | null;
}

/**
 * The answer to closing a session: the server has forgotten it.
 *
 * Attributes:
 *   id: The id of the session closed.
 */
export interface SessionClosed {
  id: string;
}

/**
 * The fixed properties of a session.
 *
 * Attributes:
 *   id: The session's identifier.
 *   game: The game's short name.
 *   parameters: The game's parameters, defaults included.
 *   num_seats: The number of seats.
 *   chance_policy: How chance nodes are resolved.
 *   turn_based: Whether a simultaneous game is served through the turn-based
 *     wrapper, which has its seats act one after another.
 *   hides_information: Whether some seat may not see the full state. When
 *     false, every viewer is omniscient.
 *   seed: The chance generator's seed; null for every viewer but the oracle,
 *     since it determines every chance outcome to come.
 *   controllers: The controllers that can play a seat of this game.
 */
export interface SessionInfo {
  id: string;
  game: string;
  parameters: Record<string, boolean | number | string>;
  num_seats: number;
  chance_policy: ChancePolicy;
  turn_based: boolean;
  hides_information: boolean;
  seed: number | null;
  controllers: Controller[];
}

/**
 * The state of a session's live game.
 *
 * Attributes:
 *   PLAYING: The game is in progress.
 *   PAUSED: A seat's controller failed; play resumes only after an undo, a
 *     reset or a change of that seat's controller. A seat whose controller
 *     could not be built (`SeatStatus.UNAVAILABLE`) resumes only after a
 *     change of its controller.
 *   TERMINAL: The game is over.
 */
export type SessionStatus = 'playing' | 'paused' | 'terminal';

/**
 * Who acts at a position.
 *
 * Attributes:
 *   kind: Whether a seat or chance acts, or the game is over.
 *   seat: The acting seat when `kind` is `seat`, otherwise null.
 */
export interface ToMove {
  kind: MoverKind;
  seat: number | null;
}

/**
 * The audience a frame is built for.
 *
 * Attributes:
 *   kind: Whether the viewer holds a seat, watches, or sees everything.
 *   seat: The viewer's seat when `kind` is `seat`, otherwise null.
 */
export interface Viewer {
  kind: ViewerKind;
  seat: number | null;
}

/**
 * Who a frame is built for.
 *
 * Attributes:
 *   SEAT: A player, who sees what that player may observe.
 *   SPECTATOR: A watcher in no seat, who sees only public state.
 *   ORACLE: An omniscient observer, who sees the full state.
 */
export type ViewerKind = 'seat' | 'spectator' | 'oracle';
