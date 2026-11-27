<!-- Modified for Doggybank from OpenSpiel. -->

# Remote bots

A bot is an HTTP server. Run the example with `python -m
doggybank_server.remote_bot_server --port 9001 --bot
doggybank_server.poker_bot:make_call_bot` and give a seat the `remote`
controller with `{"url": "http://localhost:9001"}`.

## The protocol

| Request | Body | Answer |
| ------- | ---- | ------ |
| `GET /health` | none | Any 2xx JSON when ready, such as `{"ok": true}`. Called when the seat is given the bot. |
| `POST /move` | `{"seat", "seed", "observation"}` | `{"action": <id>}` |

`observation` is the seat's private view of the hand (see the engine's
observation schema): cards, stacks, bets, pots, the public betting history
and the legal actions as `actions`, each `{"id", "kind", "amount"}`. Other
seats' hole cards are `null`. `seed` changes from move to move and is the
same at the same position, so a bot that draws from it plays reproducibly.

A seat's settings are `url` and `timeout_seconds` (0 waits as long as the
move budget allows).

The answer may instead be `{"actions": [<id>, ...]}`, of which the first is
played. It may add `"notice"`: plain text of at most 200 characters about
the move, which the seat's own viewer and omniscient viewers see. Other
fields, apart from the bot output below, are ignored.

A reply with HTTP 400, 409 or 422, or a 2xx reply with `"error"` set, is a
refusal (`{"error": ..., "reason": ...}`), and the seat fails with
`RemoteBotRefusedError`. Any other status, no connection, or no answer within
the timeout fails it with `RemoteBotUnreachableError`; a malformed reply, or
an action that is not legal, with `RemoteBotReplyError`. Nothing is retried.
What went wrong reaches only omniscient viewers (`failure.message`).

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
