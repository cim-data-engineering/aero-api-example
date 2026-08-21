# aero-api-example

Two Python scripts showing how to call the PEAK platform API
(`https://api.cimenviro.com`):

| Script | What it does |
|---|---|
| `scripts/get_token.py` | logs in with username, password and TOTP code, prints an offline token |
| `scripts/get_sites.py` | swaps that token for an access token, then calls `GET /sites` |

Each script is standalone — read it top to bottom and copy it into your own code.
Runs on Windows, macOS and Linux; the only prerequisite is
[uv](https://docs.astral.sh/uv/).

## 1. Install uv

**Windows** (PowerShell): `winget install --id=astral-sh.uv -e`
**macOS**: `brew install uv`
**Linux**: `curl -LsSf https://astral.sh/uv/install.sh | sh`

Open a new terminal so `uv` is on `PATH`, then:

```
git clone git@github.com:cim-data-engineering/aero-api-example.git
cd aero-api-example
uv sync
```

`uv sync` creates `.venv`, installs `httpx` and `python-dotenv`, and downloads
Python itself if the machine doesn't have it. Every command below is `uv run …`,
which uses `.venv` for you — no activating, no `pip install`.

## 2. Get an offline token

```
uv run scripts/get_token.py
```

It prompts for your PEAK username, your password (not echoed) and a TOTP code
from your authenticator app, then prints an **offline token** — a refresh token
that stays valid until it is revoked. Copy it into a file named `.env` in the
repo root:

```
OFFLINE_TOKEN_ACCESS=eyJhbGciOi…
```

`.env` is gitignored. Treat the token like a password: it is enough to call the
API as you, so don't commit it or paste it into a chat.

This is `grant_type=password` with `scope=openid offline_access` — the same call
as:

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

## 3. Call the API

```
uv run scripts/get_sites.py
```

It prints one line per site:

```
   411  Example Plaza
   415  Example Tower
```

Two steps happen inside: `get_access_token()` posts the offline token back as
`grant_type=refresh_token` to get a short-lived access token, then `get_sites()`
sends that as `Authorization: Bearer …` to `GET /sites`. Access tokens last 24 h
on this realm, so a script mints a fresh one each run rather than storing it.

To call another endpoint, copy `get_sites()` and change the path — the bearer
header is the only auth involved. `api-reference.md` records what has been
verified about `GET /sites` itself: which filters work, how paging behaves, and
which ones the server ignores instead of rejecting.

## Windows

The Python is portable; only the shell differs. In PowerShell:

```powershell
uv sync
uv run scripts\get_token.py
uv run scripts\get_sites.py
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| `login failed: HTTP 401 … Invalid user credentials` | wrong username or password, or a stale TOTP code — the realm reports all three the same way. Read the code immediately before pressing Enter |
| `token exchange failed: HTTP 400 … invalid_grant` | the offline token was revoked or its session went idle — run `get_token.py` again |
| `no OFFLINE_TOKEN_ACCESS in .env` | step 2 — the `.env` file is missing or the line is misspelt |
| `GET /sites failed: HTTP 401` | the token is valid but the account lacks permission for the endpoint |
| `GET /sites failed: HTTP 504` | the API gateway timed out — the unfiltered query is slow; add a filter such as `params={"site_ids": [411]}` |
