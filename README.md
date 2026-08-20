# aero-api-example

Python examples for the PEAK platform API (`https://api.cimenviro.com`) — a small
`peak` package for auth and sites, plus CLI scripts that use it.

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

## Quick start

```bash
uv sync                                      # create .venv and install
uv run scripts/get_token.py --length         # prove auth works, print no secret
```

That second command needs an offline token. If it says `no offline token found`,
do step 2 below.

## 1. Install

```bash
uv sync                  # runtime deps
uv sync --extra dev      # + ruff and pre-commit
uv run pre-commit install
```

## 2. Create an offline token

The scripts never hold your password. Auth is a two-stage OAuth exchange against
Keycloak:

- an **offline token** — a long-lived refresh token you mint once and keep on disk,
- an **access token** — short-lived (24 h on this realm), minted from the offline token
  on each run and cached.

Mint the offline token with your PEAK username and password:

```bash
read -rs -p 'PEAK password: ' PEAK_PASSWORD; echo
curl -s -X POST https://login.cimenviro.com/auth/realms/cimenviro/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=api-external \
  -d scope=offline_access \
  -d username='you@cimenviro.com' \
  --data-urlencode "password=$PEAK_PASSWORD" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["refresh_token"])'
unset PEAK_PASSWORD
```

The `refresh_token` in the response **is** the offline token. `scope=offline_access`
is what makes it long-lived; without it you get an ordinary refresh token that dies
with the session.

Save it outside the repo, readable only by you:

```bash
mkdir -p ~/.local/secrets
# paste the token, then Ctrl-D
cat > ~/.local/secrets/aero_api
chmod 600 ~/.local/secrets/aero_api
```

`aero_api` is the file the tools read by default. The convention is
`~/.local/secrets/<tenant>_api`, so a second tenant goes in
`~/.local/secrets/benmax_api` and is selected with `--tenant benmax`.

An offline token stays valid until it is revoked or its Keycloak offline session
goes idle for longer than the realm allows. When exchanges start failing with
`invalid_grant`, mint a new one with the command above.

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

with core_client() as api:                      # carries the bearer token
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
| `HTTP 401` on an API call, token decodes fine | the token is valid but lacks the permission; check `check_auth.py` realm roles |
| `unknown site filter(s): …` | filter name not accepted by `GET /sites`; the error lists the valid ones |
