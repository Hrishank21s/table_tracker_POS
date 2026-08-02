# Weekend Rush — Snooker & Table Tracker POS

Flask REST API + decoupled Tailwind/vanilla-JS frontend for running a snooker hall:
live per-table clocks, play/pause/stop billing with bill splitting, customer
membership + NFC records, table/user administration and public booking requests.

## Layout

```
weekend-rush/
├── backend/            Flask API (SQLite, JWT, bcrypt)
│   ├── app.py          app factory, blueprint registration, auto-seed
│   ├── models.py       User, TableData, SessionLog, Customer, Booking
│   └── api/            auth, tables, customers, settings, booking blueprints
└── frontend/           static pages (no build step)
    ├── public.html             club landing, live floor + booking dashboard
    ├── admin_login.html        staff/admin login
    ├── dashboard_floors.html   floor tabs + table controls
    ├── customers.html          customer CRUD, membership, NFC
    ├── settings.html           tables (floor/rate) + user management
    ├── css/public-theme.css     club theme (shared base)
    ├── css/styles.css           staff console components
    └── js/                      api.js (fetch wrapper + JWT), shell.js (auth guard,
                                 header clock, role locking), login.js, dashboard.js,
                                 customers.js, settings.js, public.js
```

## Run the backend

```bash
cd weekend-rush/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py            # http://localhost:5000
```

On first start the SQLite DB is created and seeded with an `admin/admin` user and
9 tables (3 per floor, ₹3.00/hour).

## Run the frontend

```bash
cd weekend-rush/frontend
python3 -m http.server 8080
```

Open http://localhost:8080/public.html (public board) or
http://localhost:8080/admin_login.html (staff/admin).

## Real-time clocks

Every table card renders a live `HH:MM:SS` counter driven by the server-reported
`accumulated_seconds` + `active_start`. The frontend measures the offset between
server time and browser time on every poll, so the counters stay accurate across
pause/resume cycles and clock skew. A wall clock is shown in every page header.

## Billing

`accumulated_seconds` grows on each pause; the running segment is added live.
`POST /api/tables/<id>/stop` computes
`amount = (total_seconds / 3600) * current_rate`, writes a `SessionLog`, resets the
table to `idle`, and returns the total plus the per-person split in INR.

## API summary

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | – | JWT for admin/staff |
| GET | `/api/auth/me` | token | current user |
| GET | `/api/tables/` | – | tables grouped by floor |
| POST | `/api/tables/<id>/play` \| `/pause` \| `/stop` | token | session control |
| GET | `/api/tables/logs` | token | recent session logs |
| GET/POST/PUT/DELETE | `/api/customers/...` | token | customer CRUD |
| POST | `/api/customers/<id>/toggle-member` \| `/nfc` | token | membership / NFC |
| GET/POST/PUT/DELETE | `/api/settings/tables...` | admin for writes | tables, floors, rates |
| GET/POST/PUT/DELETE | `/api/settings/users...` | admin | user management |
| POST | `/api/booking/request` | – | booking with 12-char UPI UTR |
| GET/POST | `/api/booking/`, `/api/booking/<id>/confirm` | token | booking review |

## Notes

- Every page shares one club theme: lime-on-charcoal, DM Mono clocks, pill buttons and
  status tags (`idle`, `running`, `paused`, `booked`).
- No `alert()`, `confirm()` or `prompt()` anywhere — all feedback is inline DOM text
  (plus a non-blocking toast on the public booking form).
- Staff role sees read-only rates/users; admin-only controls are disabled and the
  server enforces the same rule.
