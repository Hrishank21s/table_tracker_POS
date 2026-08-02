import os
import secrets
import sqlite3
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

DB_PATH = os.environ.get("TRACKER_DB_PATH", "tracker.db")
API_KEY = os.environ.get("TRACKER_API_KEY", "")
ALLOW_NO_AUTH = os.environ.get("TRACKER_ALLOW_NO_AUTH", "").lower() in ("1", "true", "yes")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("TRACKER_CORS_ORIGINS", "http://localhost:8000").split(",")
    if origin.strip()
]

if not API_KEY and not ALLOW_NO_AUTH:
    raise RuntimeError(
        "TRACKER_API_KEY is not set. Set it to a random secret (see .env.example), "
        "or set TRACKER_ALLOW_NO_AUTH=1 to run without authentication on a trusted, "
        "isolated network."
    )

app = FastAPI(title="Weekend Rush Table Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Constant-time API key check. Skipped only when auth is explicitly disabled."""
    if ALLOW_NO_AUTH and not API_KEY:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )


# --- Pydantic Models for incoming JSON requests ---
class ScanRequest(BaseModel):
    rfid_tag: str = Field(min_length=1, max_length=128)

    @field_validator("rfid_tag")
    @classmethod
    def strip_tag(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("rfid_tag must not be blank")
        return value


class StartSessionRequest(BaseModel):
    table_id: int = Field(gt=0)
    customer_id: Optional[int] = Field(default=None, gt=0)


class AddItemRequest(BaseModel):
    session_id: int = Field(gt=0)
    item_id: int = Field(gt=0)


class CheckoutRequest(BaseModel):
    session_id: int = Field(gt=0)
    payment_status: Literal["PAID", "UNPAID", "CLOSE"]
    total_minutes: float = Field(ge=0, le=60 * 24 * 7)


# --- API ROUTES ---


@app.get("/")
def read_root():
    return {"status": "Server is running offline and ready."}


@app.get("/zones", dependencies=[Depends(require_api_key)])
def get_zones_and_tables(db: sqlite3.Connection = Depends(get_db)):
    """Fetches all zones and their respective tables."""
    zones = db.execute("SELECT * FROM zones").fetchall()
    result = []
    for zone in zones:
        tables = db.execute("SELECT * FROM tables WHERE zone_id = ?", (zone["id"],)).fetchall()
        result.append({"zone_name": zone["name"], "tables": [dict(t) for t in tables]})
    return result


@app.get("/menu", dependencies=[Depends(require_api_key)])
def get_menu(db: sqlite3.Connection = Depends(get_db)):
    """Fetches all quick-add menu items."""
    items = db.execute("SELECT * FROM menu_items").fetchall()
    return [dict(i) for i in items]


@app.post("/api/scan", dependencies=[Depends(require_api_key)])
def rfid_scan(scan: ScanRequest, db: sqlite3.Connection = Depends(get_db)):
    """ESP32 hits this endpoint when an RFID card is tapped."""
    customer = db.execute(
        "SELECT id, name, debt_amount FROM customers WHERE rfid_tag = ?", (scan.rfid_tag,)
    ).fetchone()
    if customer:
        return {"status": "success", "customer": dict(customer)}
    return {"status": "not_found", "message": "Unregistered Card"}


@app.post("/sessions/start", dependencies=[Depends(require_api_key)])
def start_session(req: StartSessionRequest, db: sqlite3.Connection = Depends(get_db)):
    """Starts a new timer/session for a specific table."""
    cursor = db.cursor()
    table = cursor.execute("SELECT id, status FROM tables WHERE id = ?", (req.table_id,)).fetchone()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    if table["status"] == "ACTIVE":
        raise HTTPException(status_code=409, detail="Table already has an active session")

    if req.customer_id is not None:
        customer = cursor.execute(
            "SELECT id FROM customers WHERE id = ?", (req.customer_id,)
        ).fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

    cursor.execute("UPDATE tables SET status = 'ACTIVE' WHERE id = ?", (req.table_id,))
    cursor.execute(
        """
        INSERT INTO sessions (table_id, customer_id, start_time)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """,
        (req.table_id, req.customer_id),
    )
    session_id = cursor.lastrowid
    db.commit()
    return {"status": "started", "session_id": session_id}


@app.post("/sessions/add_item", dependencies=[Depends(require_api_key)])
def add_item(req: AddItemRequest, db: sqlite3.Connection = Depends(get_db)):
    """Adds a menu item (like Tea or Coffee) to an active session."""
    cursor = db.cursor()
    session = cursor.execute(
        "SELECT id, end_time FROM sessions WHERE id = ?", (req.session_id,)
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["end_time"] is not None:
        raise HTTPException(status_code=409, detail="Session is already closed")

    item = cursor.execute(
        "SELECT name, price FROM menu_items WHERE id = ?", (req.item_id,)
    ).fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    cursor.execute(
        """
        INSERT INTO session_items (session_id, item_name, price)
        VALUES (?, ?, ?)
    """,
        (req.session_id, item["name"], item["price"]),
    )
    cursor.execute(
        """
        UPDATE sessions SET items_cost = items_cost + ? WHERE id = ?
    """,
        (item["price"], req.session_id),
    )

    db.commit()
    return {"status": "item_added", "item": dict(item)}


@app.post("/sessions/checkout", dependencies=[Depends(require_api_key)])
def checkout_session(req: CheckoutRequest, db: sqlite3.Connection = Depends(get_db)):
    """Closes the table, calculates the final bill, and logs debt if UNPAID."""
    cursor = db.cursor()

    session = cursor.execute(
        """
        SELECT s.*, t.rate_per_minute
        FROM sessions s
        JOIN tables t ON s.table_id = t.id
        WHERE s.id = ?
    """,
        (req.session_id,),
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["end_time"] is not None:
        raise HTTPException(status_code=409, detail="Session is already closed")

    time_cost = req.total_minutes * session["rate_per_minute"]
    total_bill = time_cost + session["items_cost"]

    if req.payment_status == "UNPAID" and session["customer_id"]:
        cursor.execute(
            """
            UPDATE customers SET debt_amount = debt_amount + ? WHERE id = ?
        """,
            (total_bill, session["customer_id"]),
        )

    cursor.execute(
        """
        UPDATE sessions
        SET end_time = CURRENT_TIMESTAMP, total_minutes = ?, time_cost = ?, total_bill = ?, payment_status = ?
        WHERE id = ? AND end_time IS NULL
    """,
        (req.total_minutes, time_cost, total_bill, req.payment_status, req.session_id),
    )
    if cursor.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="Session is already closed")

    cursor.execute("UPDATE tables SET status = 'AVAILABLE' WHERE id = ?", (session["table_id"],))

    db.commit()
    return {"status": "closed", "final_bill": total_bill, "payment_status": req.payment_status}
