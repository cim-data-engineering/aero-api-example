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
git clone https://github.com/cim-data-engineering/aero-api-example.git
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

It prints the active sites, one per line, minus any assigned to the client named
in `EXCLUDE_CLIENT_NAME` (the bucket buildings get parked in when they leave the
platform — change the name to match your customer):

```
     3  99 Elizabeth St
    16  193 North Quay
    20  6-7 Eden Park Drive
```

Four steps, one function each, all commented in the file:

1. `get_access_token()` posts the offline token back as `grant_type=refresh_token`
   and gets a short-lived access token. These last 24 h on this realm, so the
   script mints one per run rather than storing it.
2. `get_client_id()` calls `GET /users/clients?client_name=…`. Sites carry client
   *ids* only, and the users service is the only place names live.
3. `get_all_sites()` pages through `GET /sites?is_active=true` by cursor — the
   cursor is the last `site_id` seen, and `order_by_site_id=true` is required
   alongside it. A short page means the end.
4. Sites whose `clients` list holds that id are dropped; the rest are printed.

To call another endpoint, copy `api_get()` and change the path — the bearer header
is the only auth involved. Field names come from the live Swagger JSON, linked at
the top of `api-reference.md`; don't guess them. That file also records what the
schema doesn't say: `limit=25` is what `GET /sites` reliably answers (bigger pages
time out), array filters must repeat the key, and `site_name` is exact-match.

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
