# Weekend Rush Table Tracker POS

Offline-first point of sale for a snooker/pool parlour: a FastAPI + SQLite backend and a
single-page HTML frontend that tracks per-table timers, quick-add menu items, bill splitting
and PAID / UNPAID / CLOSE checkouts (with debt tracking for RFID-registered customers).

## Requirements

- Python 3.9+
- A browser (the frontend is a single static `index.html`)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload
```

The API starts on http://localhost:8000 and creates/seeds `tracker.db` on boot
(3 zones, 6 tables, 4 menu items) — no separate setup step is needed. Interactive API
docs are at http://localhost:8000/docs.

Then open `index.html` in a browser (double-click it, or `python3 -m http.server 5500`
and visit http://localhost:5500/index.html). The frontend talks to `http://localhost:8000`;
change `API_URL` at the top of the `<script>` block if you host the API elsewhere.

Set `TRACKER_DB` to store the database somewhere else:

```bash
TRACKER_DB=/var/lib/weekendrush/tracker.db uvicorn main:app
```

`python3 init_db.py` can still be run manually; it is safe to re-run and never duplicates
or overwrites existing rows.

## Tests

```bash
pip install -r requirements-dev.txt
pytest                                    # or: pytest --cov=main --cov=init_db
```

## API

| Method | Path                  | Purpose                                                        |
| ------ | --------------------- | -------------------------------------------------------------- |
| GET    | `/`                   | Health check                                                    |
| GET    | `/zones`              | Zones with their tables (id, name, rate, status)                |
| GET    | `/menu`               | Quick-add menu items                                            |
| POST   | `/api/scan`           | Look up a customer by RFID tag (used by the ESP32 reader)       |
| POST   | `/sessions/start`     | Start a table timer; optional `rate_per_minute` sets the rate   |
| POST   | `/sessions/add_item`  | Add a menu item to a running session                            |
| POST   | `/sessions/checkout`  | Close a session as `PAID`, `UNPAID` (adds debt) or `CLOSE`      |

Billing: `total_bill = total_minutes * tables.rate_per_minute + sessions.items_cost`.

Errors: unknown table/customer/session/item → `404`; starting a table that is already `ACTIVE`, or
adding an item to / checking out an already-closed session → `409`; invalid `payment_status` or a
negative `total_minutes` → `422`; database unavailable → `503`. The frontend surfaces the `detail`
of any failure in an alert and leaves the table state untouched, so a failed request is never
silently billed or logged.
