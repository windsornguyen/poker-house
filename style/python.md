# Python style

Ruff and `ty` enforce what they can, and `pnpm check` runs both. The rest is care:
types that say exactly what a value can be, and errors that say exactly what went wrong.

## Limits

Functions stay under 70 lines and files under 500. Nesting stays under 3 levels, and
arguments under 5. Hitting a limit means the code wants another function, type or module.

## Functions

- Return early instead of nesting.
- Check one condition per error, so the error names the clause that failed.
- A function does one thing. If its name needs "and", it is two functions.
- Put the return value in a named variable when it helps a debugger.
- Behavior lives on the type that owns the state it reads. Loose functions that keep taking
  the same object belong on that object's class.
- Arguments past the first one or two are keyword-only (`*,`), so a changed default never
  silently changes a call.

## Naming

Names are precise: `get_user_by_id(user_id)`, not `get_usr(uid)`. Units and qualifiers go
last: `timeout_seconds`, `stack_max`. Mechanical locals (temporaries, responses, loop
counters) get short Unix names (`res`, `ret`, `row`). Domain values get the domain's name
(`stack`, `buy_in`, `holder`).

## Types

- Everything is typed. `ty check` passes.
- No raw `dict[str, Any]` crossing a function boundary. Use a frozen dataclass or a
  pydantic model.
- Pydantic at the edges, where JSON enters and leaves (`request.py`, `contract.py`).
  Plain frozen dataclasses inside.
- No `object` annotations and no unexplained `Any`. A polymorphic value is a `Protocol`
  or a union.
- Illegal states are unrepresentable: an enum, not a string with five allowed values.

## Docstrings and comments

Google-style docstrings state the contract: what the function does, then `Args`,
`Returns` and `Raises` when they add something. Comments explain why, never what. A
comment that restates the code is deleted.

## Errors

Fail fast and loud. Raise the typed errors in `errors.py`, each with a full-sentence
message a player can read. Catch only the specific exception you expect, at the boundary
that owns it. Never write `except Exception`, and never swallow an error.

No fallbacks. When the primary path is unavailable, the operation fails with an error that
names it. It never switches to a different implementation, retries a different way, or
degrades quietly. Two modes for one feature means the bug hides in the one nobody tests.

## Wait on events, never spin

Block on the event, never on a `time.sleep` loop that checks whether it happened: a
`threading.Condition`, a queue, `select`/epoll on a socket, or Postgres `LISTEN`. A
shortage of something refuses at once with a typed error rather than waiting for it.

## Tests

Integration tests against real Postgres (`tests/cluster.py`), no mocks of our own code.
A property test states its invariants and is proven by a mutant that breaks each guard.
