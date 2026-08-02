from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

DB_PATH = "tracker.db"

# Small tolerance (in minutes) when validating client-reported elapsed time
# against the server's wall-clock, to absorb clock skew / rounding.
MINUTE_TOLERANCE = 1.0

app = FastAPI(title="Weekend Rush Table Tracker API")

# Allow the HTML frontend to talk to this server.
# NOTE: credentials are disabled on purpose; the spec forbids
# allow_origins=["*"] together with allow_credentials=True.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helper function to get database connection
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Returns rows as dictionaries
    conn.execute("PRAGMA foreign_keys = ON")  # Enforce declared foreign keys
    try:
        yield conn
    finally:
        conn.close()


class PaymentStatus(str, Enum):
    PAID = "PAID"
    UNPAID = "UNPAID"
    CLOSE = "CLOSE"


# --- Pydantic Models for incoming JSON requests ---
class ScanRequest(BaseModel):
    rfid_tag: str


class StartSessionRequest(BaseModel):
    table_id: int
    customer_id: Optional[int] = None
    rate_per_minute: Optional[float] = None

    @field_validator("rate_per_minute")
    @classmethod
    def rate_must_be_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError("rate_per_minute must be positive")
        return v


class AddItemRequest(BaseModel):
    session_id: int
    item_id: int


class CheckoutRequest(BaseModel):
    session_id: int
    payment_status: PaymentStatus
    total_minutes: float
    rate_per_minute: Optional[float] = None

    @field_validator("total_minutes")
    @classmethod
    def minutes_not_negative(cls, v):
        if v < 0:
            raise ValueError("total_minutes cannot be negative")
        return v

    @field_validator("rate_per_minute")
    @classmethod
    def rate_must_be_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError("rate_per_minute must be positive")
        return v


def _parse_sql_timestamp(value: str) -> datetime:
    """Parse a SQLite CURRENT_TIMESTAMP ('YYYY-MM-DD HH:MM:SS', UTC) value."""
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)


# --- API ROUTES ---

@app.get("/")
def read_root():
    return {"status": "Server is running offline and ready."}


@app.get("/zones")
def get_zones_and_tables(db: sqlite3.Connection = Depends(get_db)):
    """Fetches all zones and their respective tables."""
    zones = db.execute("SELECT * FROM zones").fetchall()
    result = []
    for zone in zones:
        tables = db.execute(
            "SELECT * FROM tables WHERE zone_id = ?", (zone["id"],)
        ).fetchall()
        result.append(
            {"zone_name": zone["name"], "tables": [dict(t) for t in tables]}
        )
    return result


@app.get("/menu")
def get_menu(db: sqlite3.Connection = Depends(get_db)):
    """Fetches all quick-add menu items."""
    items = db.execute("SELECT * FROM menu_items").fetchall()
    return [dict(i) for i in items]


@app.get("/sessions/active")
def get_active_sessions(db: sqlite3.Connection = Depends(get_db)):
    """Returns open (not yet checked-out) sessions so the frontend can
    rehydrate its state after a page reload."""
    sessions = db.execute(
        "SELECT * FROM sessions WHERE end_time IS NULL"
    ).fetchall()
    result = []
    for s in sessions:
        items = db.execute(
            "SELECT item_name, price FROM session_items WHERE session_id = ?",
            (s["id"],),
        ).fetchall()
        result.append(
            {
                "session_id": s["id"],
                "table_id": s["table_id"],
                "customer_id": s["customer_id"],
                "start_time": s["start_time"],
                "rate_per_minute": s["rate_per_minute"],
                "items_cost": s["items_cost"],
                "items": [dict(i) for i in items],
            }
        )
    return result


@app.post("/api/scan")
def rfid_scan(scan: ScanRequest, db: sqlite3.Connection = Depends(get_db)):
    """ESP32 hits this endpoint when an RFID card is tapped."""
    customer = db.execute(
        "SELECT * FROM customers WHERE rfid_tag = ?", (scan.rfid_tag,)
    ).fetchone()
    if customer:
        return {"status": "success", "customer": dict(customer)}
    return {"status": "not_found", "message": "Unregistered Card"}


@app.post("/sessions/start")
def start_session(
    req: StartSessionRequest, db: sqlite3.Connection = Depends(get_db)
):
    """Starts a new timer/session for a specific table."""
    cursor = db.cursor()

    table = cursor.execute(
        "SELECT * FROM tables WHERE id = ?", (req.table_id,)
    ).fetchone()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    if table["status"] == "ACTIVE":
        raise HTTPException(
            status_code=409, detail="Table already has an active session"
        )

    if req.customer_id is not None:
        customer = cursor.execute(
            "SELECT id FROM customers WHERE id = ?", (req.customer_id,)
        ).fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

    # Rate chosen at start; falls back to the table's configured rate.
    rate = req.rate_per_minute if req.rate_per_minute is not None else table["rate_per_minute"]

    # Mark table as ACTIVE
    cursor.execute(
        "UPDATE tables SET status = 'ACTIVE' WHERE id = ?", (req.table_id,)
    )
    # Create the session
    cursor.execute(
        """
        INSERT INTO sessions (table_id, customer_id, rate_per_minute, start_time)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (req.table_id, req.customer_id, rate),
    )
    session_id = cursor.lastrowid
    db.commit()
    return {"status": "started", "session_id": session_id, "rate_per_minute": rate}


@app.post("/sessions/add_item")
def add_item(req: AddItemRequest, db: sqlite3.Connection = Depends(get_db)):
    """Adds a menu item (like Tea or Coffee) to an active session."""
    cursor = db.cursor()

    session = cursor.execute(
        "SELECT id, end_time FROM sessions WHERE id = ?", (req.session_id,)
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["end_time"] is not None:
        raise HTTPException(
            status_code=409, detail="Session already closed"
        )

    item = cursor.execute(
        "SELECT name, price FROM menu_items WHERE id = ?", (req.item_id,)
    ).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Log the item to the session
    cursor.execute(
        """
        INSERT INTO session_items (session_id, item_name, price)
        VALUES (?, ?, ?)
        """,
        (req.session_id, item["name"], item["price"]),
    )

    # Update the running items_cost in the sessions table
    cursor.execute(
        "UPDATE sessions SET items_cost = items_cost + ? WHERE id = ?",
        (item["price"], req.session_id),
    )

    db.commit()
    return {"status": "item_added", "item": dict(item)}


@app.post("/sessions/checkout")
def checkout_session(
    req: CheckoutRequest, db: sqlite3.Connection = Depends(get_db)
):
    """Closes the table, calculates the final bill, and logs debt if UNPAID."""
    cursor = db.cursor()

    session = cursor.execute(
        "SELECT * FROM sessions WHERE id = ?", (req.session_id,)
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["end_time"] is not None:
        raise HTTPException(status_code=409, detail="Session already closed")

    # Clamp client-reported minutes to the real wall-clock elapsed so the
    # bill can never exceed actual table time (pauses only ever reduce it).
    minutes = req.total_minutes
    try:
        elapsed_wall = (
            datetime.now(timezone.utc) - _parse_sql_timestamp(session["start_time"])
        ).total_seconds() / 60.0
        if minutes > elapsed_wall + MINUTE_TOLERANCE:
            minutes = max(elapsed_wall, 0.0)
    except (ValueError, TypeError):
        # If the stored timestamp is unparseable, fall back to the client value.
        pass

    # Rate precedence: explicit request rate > rate stored on the session.
    rate = (
        req.rate_per_minute
        if req.rate_per_minute is not None
        else session["rate_per_minute"]
    )
    if rate is None:
        rate = 0.0

    time_cost = round(minutes * rate, 2)
    items_cost = session["items_cost"] or 0.0
    total_bill = round(time_cost + items_cost, 2)

    # If unpaid and tied to a customer, add to their debt
    if req.payment_status == PaymentStatus.UNPAID and session["customer_id"]:
        cursor.execute(
            "UPDATE customers SET debt_amount = debt_amount + ? WHERE id = ?",
            (total_bill, session["customer_id"]),
        )

    # Finalize the session
    cursor.execute(
        """
        UPDATE sessions
        SET end_time = CURRENT_TIMESTAMP, total_minutes = ?, rate_per_minute = ?,
            time_cost = ?, total_bill = ?, payment_status = ?
        WHERE id = ?
        """,
        (minutes, rate, time_cost, total_bill, req.payment_status.value, req.session_id),
    )

    # Free up the table
    cursor.execute(
        "UPDATE tables SET status = 'AVAILABLE' WHERE id = ?", (session["table_id"],)
    )

    db.commit()
    return {
        "status": "closed",
        "final_bill": total_bill,
        "time_cost": time_cost,
        "items_cost": round(items_cost, 2),
        "total_minutes": round(minutes, 2),
        "rate_per_minute": rate,
        "payment_status": req.payment_status.value,
    }
