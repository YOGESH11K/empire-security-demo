# 👑 Empire Security Demo — College Project

A classroom demonstration of the **browser Geolocation API + FastAPI + SQLite + Leaflet map dashboard**.

**Ethics by design:** location is collected **only** after the user clicks
`[ PRESS HERE ]` and grants the browser's **native** permission dialog.
No secret collection, no background watch, no hidden iframes, no fingerprinting.

```
Landing page → navigator.geolocation.getCurrentPosition() → POST /api/location
→ FastAPI → SQLite → Dashboard (Leaflet + OpenStreetMap, 5s polling)
```

## Project structure

```
empire-security/
├── backend/
│   ├── main.py          # FastAPI app, CORS, static mounts (/, /dashboard)
│   ├── database.py      # SQLite engine + session
│   ├── models.py        # locations table
│   ├── schemas.py       # Pydantic validation
│   ├── routes/
│   │   ├── __init__.py
│   │   └── location.py  # POST/GET/DELETE + /stats + rate limit
│   └── requirements.txt
├── frontend/            # mobile-first landing page
│   ├── index.html
│   ├── style.css
│   └── app.js
├── dashboard/           # 👑 EMPIRE SECURITY DASHBOARD
│   ├── index.html
│   ├── style.css
│   └── dashboard.js
├── README.md
└── .gitignore
```

## Prerequisites

- Python 3.10+
- A modern browser (Chrome / Edge / Safari)
- Phone + laptop on the same Wi-Fi for the mobile demo (or just use localhost)

## 1. Installation

```bash
cd empire-security/backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

## 2. Run the backend

From `empire-security/backend`:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Then open:

| Page | URL |
|------|-----|
| Landing page | http://127.0.0.1:8000/ |
| Dashboard | http://127.0.0.1:8000/dashboard/ |
| API docs (Swagger) | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/api/health |

> For phones on the same LAN, replace `127.0.0.1` with your laptop's LAN IP,
> e.g. `http://192.168.1.5:8000/`. The landing page also accepts
> `?api=http://192.168.1.5:8000` to point at the backend explicitly.

### HTTPS-ready

For production, terminate TLS in front of uvicorn (nginx / Caddy), or:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile /path/to/key.pem --ssl-certfile /path/to/cert.pem
```

Geolocation requires a **secure context** (HTTPS or localhost) in most browsers.

## 3. Frontend run instructions (split-hosting alternative)

The backend already serves the frontend, so this is optional:

```bash
cd empire-security/frontend
python -m http.server 5500
# open http://127.0.0.1:5500/?api=http://127.0.0.1:8000
```

Same for the dashboard:

```bash
cd empire-security/dashboard
python -m http.server 5501
```

## 4. API documentation

Base: `http://127.0.0.1:8000`

### POST /api/location — store one consented fix

```json
{
  "latitude": 12.9716,
  "longitude": 77.5946,
  "accuracy": 25.5,
  "timestamp": "2026-10-08T12:00:00.000Z",
  "session_id": "sess_abc123XYZ_01"
}
```

- `latitude`: -90 … 90 (required)
- `longitude`: -180 … 180 (required)
- `accuracy`: 0 … 100000 m (default 0)
- `timestamp`: ISO-8601 or epoch string (required)
- `session_id`: 8–64 chars `[A-Za-z0-9_-]` (required, random, no PII)

Responses: `201` created · `422` validation error · `429` rate limited (>10/min/IP).

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/location \
  -H "Content-Type: application/json" \
  -d '{"latitude":12.97,"longitude":77.59,"accuracy":20,"timestamp":"2026-10-08T12:00:00.000Z","session_id":"sess_demo1234"}'
```

### GET /api/locations?limit=100&offset=0 — newest first

```bash
curl http://127.0.0.1:8000/api/locations?limit=10
```

### GET /api/location/{id}

```bash
curl http://127.0.0.1:8000/api/location/1
```

### DELETE /api/location/{id} — returns 204

```bash
curl -X DELETE http://127.0.0.1:8000/api/location/1 -i
```

### GET /api/stats — dashboard aggregates

```json
{"total": 3, "latest": {...}, "last_received_at": "...", "avg_accuracy": 21.5, "active_sessions": 2}
```

### GET /api/health

```json
{"status": "ok", "service": "empire-security-demo"}
```

## 5. Testing instructions (checklist)

1. [ ] Open landing page (`/`). Confirm "Congratulations! 10K Followers" + `[ PRESS HERE ]`.
2. [ ] Press `[ PRESS HERE ]` → browser shows its **native** location permission dialog.
3. [ ] Click **Allow** → see `✅ Security verification completed…`.
4. [ ] `GET /api/locations` contains the new record (correct lat/lon).
5. [ ] Open SQLite (`backend/empire_security.db`, table `locations`) → row exists.
6. [ ] Open `/dashboard/` → marker appears; click marker → lat/lon/accuracy/timestamp/session shown.
7. [ ] Stats (total/latest/last/avg/sessions) update within ~5s.
8. [ ] Deny flow: reload landing page → press → **Block** → `❌ Location permission was not granted` and **no** new row in `GET /api/locations`.
9. [ ] Invalid data: `POST` with `{"latitude": 999, ...}` → `422`.
10. [ ] Missing backend: stop uvicorn → press → friendly "server could not be reached" message.
11. [ ] Rate limit: send 11 POSTs in <60s from one IP → 11th returns `429`.
12. [ ] Delete: `DELETE /api/location/{id}` → `204`; `GET` again → `404`.

Quick automated smoke test (backend must be running):

```bash
# health + invalid-coords rejection + CRUD round-trip
curl http://127.0.0.1:8000/api/health
curl -X POST http://127.0.0.1:8000/api/location -H "Content-Type: application/json" -d '{"latitude":999,"longitude":0,"accuracy":0,"timestamp":"2026-10-08T00:00:00Z","session_id":"sess_test1234"}' -i
```

## 6. Deployment instructions (live: GitHub + Vercel)

**Live app = Vercel (free, always-on HTTPS link, no sleep). Code = GitHub.**

Live URLs:
- Landing: `https://empire-security.vercel.app/`
- Dashboard: `https://empire-security.vercel.app/dashboard/`

How it stays permanent:
- The app runs as a serverless FastAPI service (`vercel.json` → `backend.main:app`).
- Location data is stored in a private GitHub Gist (`GIST_ID` + `GH_TOKEN` env vars),
  so check-ins survive restarts — open the dashboard hours later, data is still there.
- Local laptop run still uses SQLite automatically (no env vars = SQLite mode).

Redeploy after code changes:
```bash
cd empire-security
vercel deploy --prod --yes
```

Notes:
- HTTPS is automatic on Vercel — phone browsers allow geolocation (plain
  `http://192.168...` LAN links are blocked by mobile browsers).
- Old alternative: `render.yaml` is kept for Render deploys, but Render's free
  tier now requires a card on file and its disk is ephemeral.

## 7. Known limitations

- SQLite: single-writer, fine for demos, not for concurrent production load.
- Rate limiting is in-memory (resets on restart, per-process only).
- Dashboard uses 5s polling, not WebSockets (acceptable for prototype per spec).
- No authentication on the admin dashboard / DELETE endpoint — anyone with the URL can read/delete (fine for a college demo on a private network, not for production).
- Geolocation needs HTTPS (or localhost) + device location services; desktop accuracy may be coarse (IP/Wi-Fi based).
- One-shot `getCurrentPosition`, not continuous tracking — by design.

## 8. Future improvements

- Login-protected dashboard (hashed passwords, never plaintext) + API tokens.
- WebSocket / SSE live push instead of polling.
- Postgres + Alembic migrations.
- Per-session consent log and "delete my data" button on the landing page.
- Accuracy heatmap, geofence alerts, CSV export.
- PWA install + offline queue of consented check-ins.

## Security notes

- CORS configured in `main.py`; tighten for public deploys.
- Pydantic validation on every field; coordinate ranges enforced.
- Random `sess_*` session IDs; no passwords stored; no unnecessary PII.
- Clear error handling for denied/unavailable/timeout/unsupported/offline/invalid/network cases.
- No permission bypass, no hidden iframes, no fingerprinting, no covert tracking.
