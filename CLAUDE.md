# CLAUDE.md

Python examples for the PEAK platform API. `src/peak/` is the library (auth, http,
sites); `scripts/` holds thin argparse CLIs over it. `README.md` is the human
getting-started guide — read it before changing anything about auth.

## Tooling

- `uv` only — `uv sync`, `uv run <script>`, `uv add <pkg>`. Never `pip install`.
- `uv run ruff check .` and `uv run ruff format .` before committing. Pre-commit runs
  both, plus `uv-lock` and commitizen on the message.
- Target is **Python 3.13** (`target-version = "py313"`), so `except (A, B):` keeps its
  parentheses — the bare `except A, B:` form is a syntax error here.

## Secrets — the one rule that matters

The offline token is a long-lived credential. It lives **outside the repo**, at
`~/.local/secrets/<tenant>_api`.

- Never print it, never paste it into a file in this repo, never write it into
  `.env.example`. The same goes for the user's password and TOTP code: no
  `--password` flag exists, and nothing reads a password from `argv`.
- When demonstrating that auth works, use `scripts/get_token.py --length` or
  `--claims`, not the bare token — output lands in transcripts.
- `.env` and `.peak/` are gitignored. Keep it that way. Access tokens are cached at
  `.peak/token-<fingerprint>.json` with mode `0600`.
- Do not write a rotated refresh token back over the user's token file. Keycloak
  returns one on exchange and `exchange_offline_token` deliberately drops it.

## Auth goes through one path

Two grants, one module. `peak.auth.login()` does `grant_type=password`
(`scope=openid offline_access`, plus `totp` when the account enforces MFA) and returns
the access token *and* the offline token to store — that is how an offline token is
created. `peak.auth.exchange_offline_token()` / `get_access_token()` do the routine
`grant_type=refresh_token` path. Both POST through `_post_form`.

Routine path: `peak.config.load_settings()` → `peak.auth.get_access_token()` →
`peak.auth.client()`. Login path: `peak.config.load_login_settings()` →
`peak.auth.login()`. Don't re-implement either exchange, and don't read
`OFFLINE_TOKEN_ACCESS` or `PEAK_PASSWORD` directly in a script.

- `resolve_offline_token` owns the precedence (argument, `--token-file`, `--tenant`,
  `OFFLINE_TOKEN_ACCESS`, `OFFLINE_TOKEN_FILE`, default tenant file). Add a new source
  there, not at a call site.
- Prompts go through `config._prompt`, which returns `""` when stdin is not a terminal
  so scripted runs fail with a clear message instead of an `EOFError` traceback.
- `write_token_file` is the only thing that writes a credential to disk: mode `0600`,
  and it refuses to overwrite without `overwrite=True`.
- `ACCESS_TOKEN_URL` and `CLIENT_ID` default in `config.py` because they are not
  secrets. New non-secret settings follow that pattern rather than becoming required.
- The access-token cache is keyed on a digest of the credential — the offline token,
  or `password:<client>:<username>` when logging in. Anything that changes which
  credential is in play must change `Settings.cache_path`, or one tenant's token gets
  served for another.
- Secret fields on `Settings` carry `repr=False`. Keep it that way: a settings object
  reaches tracebacks and log lines.

## Endpoint knowledge lives in api-reference.md

`api-reference.md` records what was verified against the live API — pagination
behaviour, filters that are silently ignored, endpoints that return 501. Read it
before adding an endpoint, and add to it when you verify something new (with the date).

Do not guess field names: the live Swagger JSON is authoritative and listed there
(`https://api.cimenviro.com/swagger.json` and the per-service variants). Fetch it
rather than inferring a schema from one response.

`peak.sites.SITE_FILTERS` exists because `GET /sites` ignores unknown filters and
returns everything, which looks like a filter that matched. A new filter must be added
to that set to be usable.

## Script conventions

Each script in `scripts/`: module docstring whose first lines are runnable examples
(it becomes `--help` via `RawDescriptionHelpFormatter`), `main() -> int`,
`raise SystemExit(main())`, and a single `except (ApiError, AuthError, ConfigError)`
that prints `error: …` to stderr and returns 1. Data goes to stdout, diagnostics to
stderr, so output stays pipeable.

## Git

Remote is `git@github.com:cim-data-engineering/aero-api-example.git` (GitHub, so `gh`
not `bb`). Branch off `main`; never commit to it directly. Conventional Commits —
`feat`, `fix`, `refactor`, `chore` with an optional scope (`feat(auth): …`).
