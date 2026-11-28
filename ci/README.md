# CI

`release.ts` generates `.github/workflows/release.yml`. Edit the TypeScript, then run
`pnpm ci:generate`. `pnpm check` fails when the two differ.

- **verify** runs `pnpm check` on every push and pull request.
- **deploy** runs on `main` only, in the `Production` environment. It deploys the
  Machine, then the site, then the docs, then smokes all three and plays two bot hands.

## Production secrets

| Secret | What |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | token `doggybank-github-deploy`: Workers on the `windsor` account, Workers Routes on doggybank.io. |
| `CLOUDFLARE_ACCOUNT_ID` | the `windsor` account |
| `DEDALUS_API_KEY` | deploys the Machine |
| `DOGGYBANK_MACHINE_ID` | the Machine that serves doggybank.io |
| `DOGGYBANK_BOT_ACCOUNTS` | the two test bots' API keys, as `{"tight": {"key": ...}, "pot_odds": {"key": ...}}` |
