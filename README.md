# aero-api-example

Python examples for the PEAK platform API (`https://api.cimenviro.com`) — a small
`peak` package for auth and sites, plus CLI scripts that use it.

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

## Quick start

```bash
uv sync                                      # create .venv and install
uv run scripts/get_token.py --login --save   # log in, store the offline token
uv run scripts/get_token.py --length         # every later run: no password needed
```

The first command prompts for username, password and TOTP code. Everything after
that reads the stored offline token.

## 1. Install

```bash
uv sync                  # runtime deps
uv sync --extra dev      # + ruff and pre-commit
uv run pre-commit install
```

## 2. Create an offline token

The scripts never store your password. Auth is a two-stage OAuth exchange against
Keycloak:

- an **offline token** — a long-lived refresh token you mint once and keep on disk,
- an **access token** — short-lived (24 h on this realm), minted from the offline token
  on each run and cached.

Mint and store the offline token in one step:

```bash
uv run scripts/get_token.py --login --save
```

It prompts for username, password (not echoed) and your TOTP code, logs in with
`grant_type=password` scoped `openid offline_access`, writes the offline token to
`~/.local/secrets/aero_api` with mode `0600`, and prints the access token. It refuses
to overwrite an existing token file unless you add `--force`.

Non-interactive, or for a second tenant:

```bash
uv run scripts/get_token.py --login --username you@cimenviro.com --totp 123456 \
  --save --token-file ~/.local/secrets/benmax_api

# credentials from the environment instead of prompts
PEAK_USERNAME=you@cimenviro.com PEAK_PASSWORD=… PEAK_TOTP=123456 \
  uv run scripts/get_token.py --login --save
```

There is no `--password` flag on purpose: a password in a flag lands in shell history
and in the process list. Pass it via `PEAK_PASSWORD` or let it prompt.

`aero_api` is the file the tools read by default. The convention is
`~/.local/secrets/<tenant>_api`, so a second tenant goes in
`~/.local/secrets/benmax_api` and is selected with `--tenant benmax`.

To see the offline token rather than save it, use `--offline-token`. The equivalent
raw call, if you would rather not use the script:

```bash
curl -X POST 'https://login.cimenviro.com/auth/realms/cimenviro/protocol/openid-connect/token' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data 'grant_type=password' \
  --data 'client_id=api-external' \
  --data 'scope=openid offline_access' \
  --data 'username=<username>' \
  --data 'password=<password>' \
  --data 'totp=<code>'
```

The `refresh_token` in that response **is** the offline token; `offline_access` is what
makes it long-lived. It stays valid until it is revoked or its Keycloak offline session
goes idle for longer than the realm allows. When exchanges start failing with
`invalid_grant`, mint a new one.

## 3. Configure (optional)

With the token in `~/.local/secrets/aero_api`, **no `.env` is needed** — the realm
URL and client id are not secrets and default in code. Copy `.env.example` to `.env`
only to override something:

| Variable | Default | Use |
|---|---|---|
| `OFFLINE_TOKEN_FILE` | — | read the offline token from this path |
| `OFFLINE_TOKEN_ACCESS` | — | the offline token inline (prefer the file — it can't be committed by accident) |
| `ACCESS_TOKEN_URL` | `https://login.cimenviro.com/auth/realms/cimenviro/protocol/openid-connect/token` | a different realm |
| `CLIENT_ID` | `api-external` | a different client |
| `CLIENT_SECRET` | — | only for a confidential client |
| `PEAK_USERNAME` / `PEAK_PASSWORD` / `PEAK_TOTP` | — | `--login` credentials without prompts; for scripted use, not for `.env` |

`.env` is gitignored. Real environment variables win over `.env`.

The offline token is looked for in this order (first hit wins):

1. `token=` passed to `load_settings()`
2. `--token-file PATH` / `token_file=`
3. `--tenant NAME` / `tenant=` → `~/.local/secrets/<name>_api`
4. `OFFLINE_TOKEN_ACCESS`
5. `OFFLINE_TOKEN_FILE`
6. `~/.local/secrets/aero_api`

## 4. Get an access token

```bash
uv run scripts/get_token.py                  # token on stdout
uv run scripts/get_token.py --length         # len=1234 — safe in a shared terminal
uv run scripts/get_token.py --claims         # who the token is for, as JSON
uv run scripts/get_token.py --json           # token + expiry + source
uv run scripts/get_token.py --verbose        # source, client_id, expiry on stderr
uv run scripts/get_token.py --cached         # reuse the cached token if still valid
uv run scripts/get_token.py --tenant benmax  # ~/.local/secrets/benmax_api
uv run scripts/get_token.py --token-file ~/.local/secrets/other_api
uv run scripts/get_token.py --login          # skip the offline token, log in instead
```

A fresh token is minted on each run unless you pass `--cached`. Feed it to other
tools either by substitution or by `eval`:

```bash
TOKEN=$(uv run scripts/get_token.py)
curl -s -H "Authorization: Bearer $TOKEN" 'https://api.cimenviro.com/sites?site_ids=411'

eval "$(uv run scripts/get_token.py --export)"   # sets PEAK_TOKEN
```

## 5. The other scripts

```bash
uv run scripts/check_auth.py                 # decode the token, then call the API for real
uv run scripts/check_auth.py --refresh       # ignore the cache
uv run scripts/fetch_sites.py --active       # sites as a table
uv run scripts/fetch_sites.py --state Illinois --csv
uv run scripts/fetch_sites.py --site-id 411 --json
uv run scripts/fetch_sites.py --count
```

`check_auth.py` is the one to run when something is wrong: it prints the subject,
scope, realm roles and expiry, then does a live `GET /users/permissions/current-user`
so a well-formed but rejected token is distinguishable from a bad exchange.

## Access-token cache

Cached in `.peak/token-<fingerprint>.json`, mode `0600`, gitignored. The filename
digests the offline token, so switching tenants can't serve a token minted for
another one. A cached token is reused until 60 s before it expires. Delete `.peak/`
to force a fresh exchange.

Keycloak may return a rotated refresh token on exchange; it is deliberately not
written back, so your offline token file stays as you wrote it.

## Using the package directly

```python
from peak import core_client, fetch_sites, site_summary

with core_client() as api:  # carries the bearer token
    for site in fetch_sites(is_active=True, api=api):
        print(site_summary(site))
```

`fetch_sites` pages by cursor and rejects filter names the endpoint doesn't accept,
rather than letting the server silently ignore them and return everything. See
`api-reference.md` for the endpoint's other traps — array filters must repeat the
key, `site_name` is exact-match, `start_index` caps pages at 25.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `no offline token found` | step 2 — nothing at `~/.local/secrets/aero_api` and no env var set |
| `token exchange failed with HTTP 400 … invalid_grant` | offline token revoked or its session went idle; mint a new one |
| `HTTP 401 … invalid_grant: Invalid user credentials` on `--login` | wrong password, or a missing/stale TOTP code — the realm reports both the same way |
| `HTTP 401` on an API call, token decodes fine | the token is valid but lacks the permission; check `check_auth.py` realm roles |
| `unknown site filter(s): …` | filter name not accepted by `GET /sites`; the error lists the valid ones |
