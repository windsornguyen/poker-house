# Poker House

A poker arena built from the OpenSpiel GUI and PokerKit adapter. Keep poker
rules in the engine dependency. Bots receive only their own structured
observations and return engine-supplied legal action IDs.

## Layout

- `apps/web`: React browser client and poker renderer.
- `apps/server`: Python HTTP server and remote bot protocol.
- `packages/python/engine`: OpenSpiel adapter around PokerKit.

Preserve upstream Apache-2.0 notices and record copied code in `NOTICE`.
Python uses two-space indentation and pyink. TypeScript uses strict types
and the client ESLint/Prettier configuration. New functions are typed.
Use the existing typed JSON contract; regenerate client types from the
Python schema. Test privacy, legal actions, and payouts before changing them.
Avoid new game rules, alternate implementations on failure, and unrelated
formatting. An unavailable structured observation is an explicit error.
