# Doggybank

A poker arena built from the OpenSpiel GUI and PokerKit adapter. Keep poker
rules in the engine dependency. Bots receive only their own structured
observations and return engine-supplied legal action IDs.

## Layout

- `apps/web`: React browser client and poker renderer.
- `apps/server`: Python HTTP API (FastAPI), sessions and the chip ledger.
- `packages/python/engine`: OpenSpiel adapter around PokerKit.

Preserve upstream Apache-2.0 notices and record copied code in `NOTICE`.
Python, TypeScript and shell follow [style/python.md](style/python.md),
[style/typescript.md](style/typescript.md) and [style/shell.md](style/shell.md). TypeScript uses strict types
and the client ESLint/Prettier configuration. New functions are typed.
Use the existing typed JSON contract; regenerate client types from the
Python schema. Test privacy, legal actions, and payouts before changing them.
Avoid new game rules, alternate implementations on failure, and unrelated
formatting. An unavailable structured observation is an explicit error.

## Commits

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org):
`type(scope): summary`, such as `fix(rooms): leave only while seated` or
`docs(agents): explain commits`. The body says why.
