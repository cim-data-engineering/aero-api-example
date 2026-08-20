# aero-api-example

Python examples for the PEAK platform API (`https://api.cimenviro.com`) — a small
`peak` package for auth and sites, plus CLI scripts that use it.

Runs on Windows, macOS and Linux. The only prerequisite is
[uv](https://docs.astral.sh/uv/) — see [Install the prerequisites](#1-install-the-prerequisites).

## Quick start

```
uv sync                                 # create .venv, install deps and Python
uv run scripts/get_token.py --login     # log in; prints your offline token
```

(no uv yet? see [step 1](#1-install-the-prerequisites))

Copy that token into `.env` as `OFFLINE_TOKEN_ACCESS=...`. Every later run needs no
password:

```
uv run scripts/get_token.py --length    # len=1234 — auth works
```

Works the same on Windows, macOS and Linux. The commands below are `bash`/`zsh`;
see [Windows](#windows) for PowerShell equivalents.

## 1. Install the prerequisites

You need **git**, **uv**, and a **Python 3.13** interpreter — uv installs Python for
you, so uv is the only real prerequisite.

### uv

**Windows** (PowerShell):

```powershell
winget install --id=astral-sh.uv -e
# or, without winget:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS**:

```bash
brew install uv
# or:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Linux**:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Open a new terminal afterwards so `uv` is on `PATH`, then check it:

```
uv --version
```

### git

Windows: `winget install --id=Git.Git -e`. macOS: `xcode-select --install` (or
`brew install git`). Linux: your package manager (`apt install git`).

### This repo

```
git clone git@github.com:cim-data-engineering/aero-api-example.git
cd aero-api-example
uv sync
```

`uv sync` creates `.venv/`, installs the dependencies from `uv.lock`, and downloads
Python 3.13 if the machine doesn't have it. It does **not** need the venv activated —
every command below is `uv run …`, which uses `.venv` automatically.

Optional, for working on the code:

```
uv sync --extra dev        # ruff + pre-commit
uv run pre-commit install  # run the hooks on commit
```

Nothing else is required — no `pip install`, no `python -m venv`, no global Python.

## 2. Create an offline token

Auth is a two-stage OAuth exchange against Keycloak:

- an **offline token** — a long-lived refresh token you mint once and keep,
- an **access token** — short-lived (24 h on this realm), minted from the offline token
  on each run and cached.

Mint the offline token by logging in. It is printed to stdout; nothing is stored:

```
uv run scripts/get_token.py --login
```

It prompts for username, password (not echoed) and TOTP code, then echoes the offline
token. Keep it in whichever place suits the machine:

```
# .env in the repo root — simplest, and gitignored
OFFLINE_TOKEN_ACCESS=eyJhbGciOi…
```

```
# or a file of your own, anywhere. Leave the path unquoted in .env so backslashes
# stay literal; forward slashes work too.
OFFLINE_TOKEN_FILE=C:\Users\you\peak-token.txt
```

On macOS and Linux, `--save` writes it to `~/.local/secrets/<tenant>_api` at mode
`0600` for you, refusing to overwrite without `--force`:

```bash
uv run scripts/get_token.py --login --save
uv run scripts/get_token.py --login --save --token-file ~/.local/secrets/benmax_api
```

That path is a POSIX convention and `chmod` cannot express owner-only on Windows, so
on Windows prefer `.env` or `OFFLINE_TOKEN_FILE`.

Non-interactive, credentials from the environment:

```bash
PEAK_USERNAME=you@cimenviro.com PEAK_PASSWORD=… PEAK_TOTP=123456 \
  uv run scripts/get_token.py --login
```

There is no `--password` flag on purpose: a password in a flag lands in shell history
and in the process list. Pass it via `PEAK_PASSWORD` or let it prompt.

Under the hood this is `grant_type=password` with `scope=openid offline_access` and a
`totp` field, which is what makes the returned `refresh_token` long-lived — the raw
call, if you would rather not use the script:

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

An offline token stays valid until it is revoked or its Keycloak offline session goes
idle for longer than the realm allows. When exchanges start failing with
`invalid_grant`, log in again.

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
uv run scripts/get_token.py --login          # log in; prints the OFFLINE token
uv run scripts/get_token.py --login --access-token   # log in; prints the access token
```

`--login` prints the offline token because that is the part worth keeping. Every other
mode prints the access token.

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

## Windows

The Python is portable; only the shell syntax differs. PowerShell equivalents:

```powershell
uv sync
uv run scripts/get_token.py --login          # prompts, echoes the offline token

# capture an access token into a variable
$env:PEAK_TOKEN = uv run scripts/get_token.py

# use it
curl.exe -H "Authorization: Bearer $env:PEAK_TOKEN" https://api.cimenviro.com/sites

# credentials without prompts
$env:PEAK_USERNAME = 'you@cimenviro.com'; $env:PEAK_PASSWORD = '…'
uv run scripts/get_token.py --login
```

Notes:

- `--export` and `eval` are `sh` constructs. In PowerShell assign to `$env:` as above.
- Put the offline token in `.env` (`OFFLINE_TOKEN_ACCESS=…`) or point
  `OFFLINE_TOKEN_FILE` at a file. `--save` still works, but its `~/.local/secrets`
  path and `0600` mode are POSIX conventions — the mode is not applied on Windows.
- The access-token cache (`.peak/`) works unchanged.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `no offline token found` | step 2 — nothing at `~/.local/secrets/aero_api` and no env var set |
| `token exchange failed with HTTP 400 … invalid_grant` | offline token revoked or its session went idle; mint a new one |
| `HTTP 401 … invalid_grant: Invalid user credentials` on `--login` | wrong password, or a missing/stale TOTP code — the realm reports both the same way |
| `HTTP 401` on an API call, token decodes fine | the token is valid but lacks the permission; check `check_auth.py` realm roles |
| `unknown site filter(s): …` | filter name not accepted by `GET /sites`; the error lists the valid ones |
