# TypeScript style

`pnpm check` formats, lints and type-checks. The compiler runs with every strict flag on
(`apps/web/tsconfig.json`): `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`,
`noPropertyAccessFromIndexSignature`, `verbatimModuleSyntax` and the rest. The rest is
care: types that say exactly what a value can be.

## Limits

Functions stay under 70 lines. Logic files stay under 400 lines and component files under
300. Nesting stays under 3 levels, and arguments under 5. A component with a dozen props,
or a file with three inlined components, is several files.

## Types

- `type`, not `interface`. Interfaces merge across files silently; types collide loudly.
  Use `interface` only to augment a third-party type.
- `unknown`, never `any`. Narrow it before use. Data from the network is `unknown` until a
  schema (zod) or the generated contract (`src/contract`) says otherwise.
- A value with a known set of shapes is a discriminated union on a literal `kind` field.
  A `switch` on it ends with `const unhandled: never = value`, so a new variant fails
  to compile until every switch handles it.
- Derive types from values with `as const` and `typeof`, so the list and the type cannot
  drift. Use `satisfies` to check a value against a type without widening it.
- Avoid `as`. A type assertion is a claim the compiler cannot check. Narrow with a guard
  (`typeof`, `in`, a `value is T` predicate) instead.
- Exported functions declare their return type.
- Wire types come from the server's JSON schema. Never hand-write a type the generator
  produces.

## Functions

Return early instead of nesting. Use a ternary only to pick a value, never to choose an
action. Run independent awaits together with `Promise.all`.

## Errors

Expected failures are part of the type: a function that can be refused returns or throws
the contract's typed error (`code`, `message`), and the caller handles each code it knows.
Catch as `catch (error: unknown)` and narrow. Never swallow an error, and never fall back
to a different path when the primary one fails. Show the player the server's message, not
a generic one.

## Naming

Files are kebab-case. Booleans read as questions (`isSeated`, `hasChips`). Units go last
(`timeoutMs`, `stackMax`).

## React

One component per file. Keep state at the lowest component that needs it. Never wait on a
`setInterval` that polls the server when a stream exists: the table follows its event
stream.
