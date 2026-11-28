# Shell style

A shell script is code. It gets a file, a header, a reviewer and `shellcheck`, like the
rest of the repository. A reader follows any script by its comments and names alone, and
reads the shell only to check it.

## Give every script its own file

A script lives in a `.sh` file beside the program that runs it, never inside a string in
TypeScript or Python. `apps/server/deploy/provision.ts` reads `setup.sh` from disk and
sends it to the Machine, so the script keeps syntax highlighting, line numbers and
`shellcheck`. Write one language per file: no `python3 -c` or `jq` programs pasted inside
a script. When the answer is structured data, the caller asks the tool for JSON and decodes
it in its own language.

## Pass input as arguments

Every value the caller knows arrives as an argument, on stdin or in the environment.
Nothing is pasted into the script's text, so a path with a space or a quote arrives intact.

## Open with a header that justifies each input

```bash
#!/bin/bash
# Install a release beside the live one and switch Caddy to it. provision.ts runs
# it on the Machine as root.
#
#   $1   deploy, retire or rollback. Retire and rollback act on the colors the
#        last deploy left.
#   DOGGYBANK_COMMIT   The release to install. A wrong commit installs code CI
#                      never checked.
set -euo pipefail
```

List positional arguments, then stdin, then environment variables, each with what it is
and what breaks when it is wrong.

## Fail on the first error

Start with `set -euo pipefail`. An expected failure says so where it happens, with
`|| true` or an `if`. Check a required variable by name before use:
`: "${DATABASE_URL:?source /etc/doggybank/db.env first}"`.

## Name globals, then use the names

Right after `set`, one block names every input, constant and list. Globals are
`readonly UPPER_SNAKE`, each with a comment. Lists are arrays (`readonly -a`), so every
use expands the same words. A global set from a command is assigned, then marked
`readonly`, so a failed command still stops the script.

## Use functions to name steps

A pipeline that needs decoding gets a function named for the question it answers, with
`local` lowercase variables. A yes-or-no function returns its answer as its status and
reads as a question: `is_live`, `has_release`. Define functions after the globals and
before the first step that calls them.

## Wait on events, never spin

A script never loops on `sleep` to see whether something happened. It blocks on the event
itself:

| Waiting for | Use |
| --- | --- |
| a service to be ready | `Type=notify` and `systemctl start`, which returns once it is ready |
| a child process | `wait "$pid"` |
| a line in a log | `journalctl -f -u NAME \| grep -m1 PATTERN` with `timeout` |
| a file | `inotifywait` |
| a port to accept | the service's own readiness, not a `curl` loop |

When nothing can signal the event, the script fails now with a named error rather than
waiting.

## Comment every block in English

Split the body into blocks with a blank line between them. Each opens with a comment that
names the outcome, never the mechanism: "Report how much the release holds", not "Print the
first field of du". Indent two spaces, `then` and `do` on the line of their `if`, `for` or
`while`.

## Report failures by name

An error goes to stderr and names what is missing, then the script exits 1. A search that
finds nothing fails; it never prints an empty result for its caller to misread.

## Check

```sh
bash -n path/to/script.sh
shellcheck path/to/script.sh
```
