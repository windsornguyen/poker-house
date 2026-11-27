<!-- Modified for Poker House from OpenSpiel. -->

# Remote bots

Run a strategy with `python -m poker_house_server.remote_bot_server --port 9001
--bot poker_house_server.poker_bot:make_call_bot`. Set its seat to `remote`,
with `state: "seat_view"`, `structured: true`, and the bot server URL.

## The remote bot protocol

Every request is sent to the seat's `url` plus a path, with the protocol
version in the `Spiel-Protocol: 1` header, so that its JSON body is exactly
the bot's input. The seat's settings are `url`, `state` (`seat_view` or
`full_state`), `checkpoint` (sent as `config.checkpoint` when not empty),
`config` (a JSON object passed on as `config`), `extras`, `tensors`,
`structured` and `timeout_seconds`. A seat whose `config` gives a
`checkpoint` other than its `checkpoint` setting is refused. A bot that
plays a checkpoint reads it from `config.checkpoint`, else from its server's
environment
(`remote_bot_server.CHECKPOINT_ENV`).

| Request | Body |
| ------- | ---- |
| `GET /health` | none; a 2xx JSON response means ready (the reference server returns `{"ok": true}`). Called when the seat is given the bot. |
| `GET /info` | none; optional. A 2xx answer `{"games": [...] \| null, "state_modes": [...]}` limits what the seat may ask for. |
| `POST /spiel/step` (`full_state`) | `{"game": str(game), "state": state.serialize(), "history": [action ids], "seat", "legal_actions", "seed", "game_encoding": {"num_distinct_actions"}, "config"}` |
| `POST /spiel/observe` (`seat_view`) | `{"game": str(game), "observation": {"information_state_string", "seat", "legal_actions", "seed"}, "config", "game_encoding": {"num_distinct_actions"}}` |

A seat-view request carries those keys and no others unless the seat asks
for more, so a strict seat-view bot, one that refuses any key it does not
take (a state or a history would hand it hidden information), accepts it.
`information_state_string` is the seat's `information_state_string(seat)`,
or null where the game provides none. With `extras` on, `observation` also
carries `observation_string` (null where the game provides none),
`legal_action_labels` (each legal action's `action_to_string`), and
`history`: the history as the seat's own frame shows it, `{"seat",
"action", "label", "public_label"}` per ply, the seat's own actions in full
and every other ply (chance included) only as its public label, in a game
that hides information. With `tensors` on, it also carries
`observation_tensor` and `information_state_tensor`, each null where the
game provides none. With `structured` on, it carries `observation_struct`,
the JSON object returned by the game's `to_observation_struct(seat)`. Its
fields are defined by the game, and contain only what that seat may observe.
For example, a poker observation can carry cards, stacks and pots as fields,
without requiring a bot to parse the information-state string. This option
requires `seat_view`: a game without structured observations is refused,
and a position whose observation is withheld fails the seat with
`RemoteBotObservationError` before a request is sent. The server never
substitutes the full state. All three options default to off, so existing
strict bot request bodies are unchanged; a strict bot refuses an addition it
does not accept. `seed` changes from ply to ply and is the same at the same
position, so a bot that draws from it moves reproducibly.

The reply is `{"action": <id>}`, or `{"actions": [<id>, ...]}`, of which the
first is played and the bot is asked again at the next position. It may add
`"notice"`: plain text of at most 200 characters about the move, such as why
the bot chose the action. The seat's own viewer and omniscient viewers see it
after the controller's name in Setup › Players (`SeatView.notice`); it has no
effect on play. Other fields, apart from the bot output below, are
ignored.

A reply with HTTP 400, 409 or 422, or a 2xx reply with `"error"` set, is a
refusal (`{"error": ..., "reason": ...}`), and the seat fails with
`RemoteBotRefusedError`. Any other status, no connection, or no answer within
the timeout fails it with `RemoteBotUnreachableError`; a reply that is not
the protocol's, or whose action is not legal, with `RemoteBotReplyError`.
Nothing is retried. As for every controller, what went wrong reaches only
omniscient viewers (`failure.message`).

### The bot output

A reply may also say why the bot chose its move, for the GUI's Bot output
panel. Three optional fields carry it; each may be left out or null:

```json
{
  "action": 12,
  "policy": [
    {"action": 12, "label": "Raise to 12", "prob": 0.71},
    {"action": 1, "label": "Call", "prob": 0.29}
  ],
  "value": 0.18,
  "decided_by": "network"
}
```

| Field | Type | Meaning |
| ----- | ---- | ------- |
| `policy` | list of `{"action", "label", "prob"}` | The bot's probabilities over the seat's legal actions, in any order. Each `action` is a legal action, named at most once; each `prob` is a number in [0, 1], and together they sum to at most 1, so a bot may send only its likeliest actions. `label` is optional; the GUI shows the game's own text for each action. |
| `value` | number | The bot's estimate of the position's value for its seat. |
| `decided_by` | text, at most 40 characters | What part of the bot chose the move, such as `network`, `search`, `scripted` (a scripted endgame) or `forced` (the only legal action). |

The server keeps them with the move's ply (`HistoryEntry.bot_output`, GUI
contract 10), and the Bot output panel shows them for the ply the History
slider is on: the policy most probable first, with the move played marked.
A seat's bot output goes only to the viewers who see its move in full: the
seat's own viewer and omniscient viewers (every viewer, in a game that hides
nothing). In a game that hides information no other seat or spectator
receives it, since a bot's policy, value and `decided_by` follow from its
hand: a poker bot's policy can reveal information about its cards. A reply whose
`policy`, `value` or `decided_by` is not as above fails the seat with
`RemoteBotReplyError`.
