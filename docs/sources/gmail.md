# Gmail source

Key: `gmail`. OAuth (`gmail.readonly`).

`startup_radar/sources/gmail.py` reads curated VC newsletters (StrictlyVC, Term Sheet, CB Insights, etc.) from a label in the user's Gmail inbox and extracts funding candidates from each message.

## Setup

Gmail is the only source that requires credentials. The `/radar` skill's Onboard action walks through the Google Cloud OAuth app creation; the short version:

1. Create an OAuth 2.0 client in Google Cloud Console.
2. Download `credentials.json` to the repo root.
3. Run `uv run startup-radar run` once — the OAuth flow opens a browser, you grant `gmail.readonly` + `spreadsheets` scopes (merged into a single `token.json` since Phase 0), and the token is cached.

The `[google]` extra pulls in `google-api-python-client`, `google-auth-httplib2`, and `google-auth-oauthlib`. Install with:

```bash
uv sync --extra google
```

## Fetch flow

1. Authenticate via cached `token.json`; refresh if expired.
2. List messages under the user's configured label (e.g. `VC/Newsletters`) since `cfg.sources.gmail.lookback_days`.
3. For each message, skip if `storage.is_processed(message_id)` — Gmail is the only source that uses per-message dedup because it reads the same inbox every run.
4. Parse HTML body with `beautifulsoup4`, run funding regexes, emit `Startup` records.
5. `storage.mark_processed(message_id)`.

## Config

```yaml
sources:
  gmail:
    enabled: true
    label: VC/Newsletters
    lookback_days: 7
```

## Gotchas

- **`token.json` refresh.** The cached token auto-refreshes via `google-auth`'s internal `requests` transport. That transport is the **one** sanctioned `requests` use inside `startup_radar/` — everything else routes through the shared `httpx.Client`.
- **Token expiry.** If the Google account revokes access or the refresh token expires, delete `token.json` and run `startup-radar run` again to re-authenticate.
- **`credentials.json` / `token.json` are `.gitignore`d.** Never commit either.
- **Storage dedup.** Gmail's `fetch(cfg, storage=...)` signature actually uses the `storage` argument; other sources receive it but don't consume it.
