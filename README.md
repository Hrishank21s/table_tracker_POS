# Weekend Rush Table Tracker POS

Offline-first POS for tracking snooker/pool table sessions, quick-add menu items and billing.
FastAPI backend (`main.py`) + single-page frontend (`index.html`), backed by SQLite.

## Setup

```bash
pip install -r requirements.txt
python init_db.py                      # creates tracker.db (not committed)
cp .env.example .env                   # then fill in TRACKER_API_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"   # generate a key
```

## Running

```bash
set -a && source .env && set +a
uvicorn main:app --host 127.0.0.1 --port 8000
```

Serve the frontend from an origin listed in `TRACKER_CORS_ORIGINS` (opening `index.html`
directly from disk sends an opaque `null` origin and will be blocked):

```bash
python -m http.server 8001            # then add http://localhost:8001 to TRACKER_CORS_ORIGINS
```

On first load the page asks for the API key and stores it in `localStorage`.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRACKER_API_KEY` | _(required)_ | Shared secret required in the `X-API-Key` header on every data endpoint. |
| `TRACKER_ALLOW_NO_AUTH` | unset | Set to `1` to start without authentication. Only for a trusted, isolated LAN. |
| `TRACKER_CORS_ORIGINS` | `http://localhost:8000` | Comma-separated list of browser origins allowed to call the API. |
| `TRACKER_DB_PATH` | `tracker.db` | SQLite database path. |

## Security notes

- The API is unauthenticated only if `TRACKER_ALLOW_NO_AUTH=1`; otherwise every endpoint except
  `/` requires `X-API-Key`. Devices such as the ESP32 RFID reader must send the same header.
- Bind the server to `127.0.0.1` or a LAN interface behind a firewall — it has no TLS, so the
  API key travels in clear text over the network.
- `tracker.db` contains customer names, phone numbers, RFID tag IDs and debts. It is
  git-ignored; never commit it, and back it up to an encrypted location.
- Rotate `TRACKER_API_KEY` by updating `.env`, restarting the server and clearing the browser's
  stored key.
