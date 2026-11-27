# Doggybank engine

This package adapts PokerKit through OpenSpiel. Import
`doggybank_engine.game` before loading `doggybank` or `doggybank_acpc`
with `pyspiel.load_game`. The latter uses ACPC action IDs; both use the same
poker rules. The adapter and its original tests are derived from OpenSpiel;
see the repository's `NOTICE`.

Python 3.12, `open-spiel==2.0.2`, and `pokerkit==0.6.3` are the tested runtime.
Keep the PokerKit version pinned: its legal bet ranges are part of the adapter
contract.

## Private observations

`state.to_observation_struct(player).to_json()` returns schema version 1.
`PokerObservation` and its nested types in `game.py` define the fields.

- Hole cards use two-character codes such as `Ac`. An opponent's hidden
  cards are null. Cards already known to the player remain visible after a
  fold or showdown; cards explicitly shown at showdown become public.
- `legal_actions` and `actions` are empty unless it is the observing player's
  turn. Submit an ID from that list, including for an all-in.
- A bet or raise descriptor's `amount` is the total commitment on the
  current street. A call or bring-in amount is the chips added. Folds and
  checks have amount zero. These units apply to both native and ACPC IDs;
  a native one-chip all-in has ID 2 but amount 1.
- `betting_history` contains only public betting events, with their street
  indices and the same amount units as action descriptors. `total_pot`
  includes outstanding bets; `pots` contains collected chips and eligibility.
- Chance and terminal nodes have no legal player actions. `current_player`
  uses OpenSpiel's player IDs, including its chance and terminal sentinels.

The full-state `to_json()` method is omniscient. It is not a bot observation.

## Tests

From the repository root after installing the workspace:

```sh
uv run --all-packages python -m unittest discover -s packages/python/engine/tests -p '*_test.py'
```
