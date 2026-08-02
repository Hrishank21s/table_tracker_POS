# Weekend Rush Table Tracker (POS)

A small offline point-of-sale / table timer for a snooker & pool parlour.
A FastAPI backend tracks tables, sessions, menu items and customer tabs;
`index.html` is a self-contained frontend that talks to it.

## Stack

- **Backend:** FastAPI + SQLite (`main.py`, `init_db.py`)
- **Frontend:** single static `index.html` (no build step)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Create / seed the local database (idempotent — safe to re-run)
python init_db.py

# Run the API (http://localhost:8000)
uvicorn main:app --reload
```

Then open `index.html` in a browser (e.g. double-click it, or serve the
folder with `python -m http.server`). The frontend expects the API at
`http://localhost:8000` (see `API_URL` in `index.html`).

## Notes

- `tracker.db` is generated locally and is **git-ignored** — run
  `python init_db.py` to (re)create it.
- The per-minute rate chosen in the UI is sent to the backend and stored on
  the session, so the displayed bill matches what is persisted.
- Billed minutes are clamped server-side to real elapsed wall-clock time, so
  the bill can never exceed actual table time (pauses only reduce it).
- Open sessions are restored on page reload via `GET /sessions/active`, so a
  refresh won't leave a table stuck as `ACTIVE`.

## API

| Method | Path                | Purpose                                  |
|--------|---------------------|------------------------------------------|
| GET    | `/zones`            | Zones and their tables                   |
| GET    | `/menu`             | Quick-add menu items                     |
| GET    | `/sessions/active`  | Open sessions (for frontend rehydration) |
| POST   | `/sessions/start`   | Start a table session                    |
| POST   | `/sessions/add_item`| Add a menu item to a session             |
| POST   | `/sessions/checkout`| Close a session and compute the bill     |
| POST   | `/api/scan`         | RFID card lookup                         |
