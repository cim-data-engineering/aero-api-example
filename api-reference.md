# PEAK API reference

The tools in this repo talk to the PEAK platform at `https://api.cimenviro.com`.
Rather than vendoring swagger snapshots (which go stale), fetch the **live**
OpenAPI/Swagger JSON below. An AI client can pull these on demand to get the
current schema for any endpoint.

| Service | Swagger JSON | Covers |
|---|---|---|
| **Core** | https://api.cimenviro.com/swagger.json | Primary platform data & operations: sites, levels, zones, meters, indoor environment, history. |
| **Tickets** | https://api.cimenviro.com/tickets/swagger.json | Alert & action tickets, related activity, and metrics. |
| **Tasks** | https://api.cimenviro.com/tasks/swagger.json | Rules, templates, template categories, and task history. |
| **Users** | https://api.cimenviro.com/users/swagger.json | Users, clients, permissions (Keycloak-backed). **The only source of client *names*** — `GET /users/clients` returns `client_id`, `client_name`, `is_active`, `customer_id`. |
| **Notifications** | https://api.cimenviro.com/notifications/swagger.json | Event notifications via webhook subscriptions. |

## Clients: id ↔ name

The core data API (and the GraphQL `sites` query) only ever expose client **ids** —
a site carries `clients: [19]`, never a name. To match a client by **name** (e.g.
excluding the "ZZ-Other Buildings" churn bucket), resolve names via the **users**
service, which is the only endpoint that returns them:

```
GET /users/clients?first=0&max=500        # all clients: {client_id, client_name, is_active, customer_id}
GET /users/clients?customer_id=1          # scope to a customer
```

`lib/clients.js` wraps this (`fetchClients`, `clientsMatchingName`); `scripts/fetch-active-sites.js`
uses it to exclude churned sites by name across tenants (the id differs per tenant, the name doesn't).

## Users & preferences (users service)

`lib/users.js` wraps the user endpoints:

```
GET   /users/users?customer_id= | client_id= | contractor_id=   # users for an entity
GET   /users/users/{id}?include_entity=true                     # user by id (+ its entity)
GET   /users/users/{id}/preferences                             # incl. site_notification_options
PATCH /users/users/{id}/preferences                             # deep-merges; empty body; null clears a key
GET   /users/permissions/current-user                           # caller's effective permissions
GET   /users/permissions/{customers|clients}/{id}               # role -> {users, groups} mapping
```

There is no per-user permissions endpoint — a user's roles come from their entity's
permission mapping (contractor entities have none).

### Notifications: action vs alert are two separate resources

Per-site notifications are split across two services:

- **Action / ticket** notifications — users service, `preferences.site_notification_options`:
  a map of `site_id → "ALL_NOTIFICATIONS" | "ASSIGNED" | "NO_NOTIFICATIONS"`. PATCH
  merges per key (pass only the sites you want to change; `null` clears a key).
  Wrapped by `lib/users.js` `setSiteNotifications`.
- **Alert** notifications — notifications service, `lib/notifications.js`:

```
GET  /notifications/sites-notifications/preferences?user_id=&type=alert&start_index=0
POST /notifications/sites-notifications/preferences    # upsert: include row id to update, omit to create
```

  A row is `{ user_id, site_id, type: "alert", value }` with value
  `"ALL_NOTIFICATIONS" | "NO_NOTIFICATIONS"`.

⚠️ The notifications per-id endpoints are **not implemented server-side**:
`GET`/`DELETE /preferences/{id}` → 404, `PUT` → 501, collection `DELETE` → 405.
So alert-preference rows can be created/toggled but **not deleted**;
`NO_NOTIFICATIONS` is the "off" state.

## Sites: pagination and filters (`GET /sites`, core)

Verified against the live endpoint, 2026-08-20:

- **No `limit` and no `start_index` returns every matching site** in one response
  (57 here), with no `response_metadata`.
- **`start_index` switches on offset paging** and is the only way to get
  `response_metadata.record_count` (the total) — but it caps the page at **25**
  unless `limit` is also sent.
- **`cursor` is keyset paging on `site_id`, exclusive** — pass the last id you saw.
  It is rejected with HTTP 400 unless `order_by_site_id=true` is also set:
  `Cannot query sites using cursor when order_by_site_id is not set to true.`
- **Array filters repeat the key**: `site_ids=411&site_ids=412`. The bracket form
  `site_ids[]=411` is **silently ignored** — the response is every site, which
  looks like a filter that matched everything. Comma-joined values 400.
- **`site_name` is an exact match**, not a substring search. Filter client-side
  for partial names.
- `client_id` is null on most site records; the client ids live in the `clients`
  array. Names still come only from the users service.
- **The comfort band has no unit on the site record.** `thermal_comfort_min_temp` /
  `_max_temp` are bare numbers, and both scales appear across USA sites (20-23.3
  and 67-75), so the unit is not inferable from `/sites`. It lives on the thermal
  comfort score responses (`ThermalComfortSiteScore.unit` / `unit_id`).

`src/peak/sites.py` wraps this: `iter_sites` does the cursor loop,
`fetch_sites_page` is the offset form when the total is needed, and unknown
filter names raise rather than being dropped by the server.

## Base URLs used by this repo

Defined once in `lib/http.js`:

- Core: `https://api.cimenviro.com`
- Tickets: `https://api.cimenviro.com/tickets/tickets`
- Statuses: `https://api.cimenviro.com/tickets/statuses`
- Tasks: `https://api.cimenviro.com/tasks`

## Auth

All requests use an OAuth **refresh-token** exchange: the long-lived
`OFFLINE_TOKEN_ACCESS` is swapped for a short-lived access token on each run
(`getAccessToken` in `lib/http.js`). Credentials come from `.env` — see
`.env.example`.
