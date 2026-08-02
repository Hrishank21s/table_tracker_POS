from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("TRACKER_DB_PATH", str(Path(__file__).resolve().parent / "tracker.db"))

VALID_PAYMENT_STATUSES = ("PAID", "UNPAID", "CLOSE")

app = FastAPI(title="Weekend Rush Table Tracker API")

# Allow your HTML frontend to talk to this server without security blocks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(sqlite3.Error)
def sqlite_exception_handler(request: Request, exc: sqlite3.Error) -> JSONResponse:
    """Turns unexpected database failures into a 503 instead of an opaque 500."""
    logger.error(
        "Database error while handling %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


# Helper function to get database connection
def get_db():
    try:
        conn = sqlite3.connect(DB_PATH)
    except sqlite3.Error:
        logger.exception("Could not open the database at %s", DB_PATH)
        raise HTTPException(status_code=503, detail="Database unavailable")

    conn.row_factory = sqlite3.Row  # Returns rows as dictionaries
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    except Exception:
        # Never leave a half-applied multi-statement write behind.
        try:
            conn.rollback()
        except sqlite3.Error:
            logger.exception("Rollback failed for %s", DB_PATH)
        raise
    finally:
        conn.close()


# --- Pydantic Models for incoming JSON requests ---
class ScanRequest(BaseModel):
    rfid_tag: str = Field(min_length=1)

class StartSessionRequest(BaseModel):
    table_id: int
    customer_id: Optional[int] = None

class AddItemRequest(BaseModel):
    session_id: int
    item_id: int

class CheckoutRequest(BaseModel):
    session_id: int
    payment_status: str # 'PAID', 'UNPAID', or 'CLOSE'
    total_minutes: float = Field(ge=0)

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
        tables = db.execute("SELECT * FROM tables WHERE zone_id = ?", (zone['id'],)).fetchall()
        result.append({
            "zone_name": zone['name'],
            "tables": [dict(t) for t in tables]
        })
    return result

@app.get("/menu")
def get_menu(db: sqlite3.Connection = Depends(get_db)):
    """Fetches all quick-add menu items."""
    items = db.execute("SELECT * FROM menu_items").fetchall()
    return [dict(i) for i in items]

@app.post("/api/scan")
def rfid_scan(scan: ScanRequest, db: sqlite3.Connection = Depends(get_db)):
    """ESP32 hits this endpoint when an RFID card is tapped."""
    customer = db.execute("SELECT * FROM customers WHERE rfid_tag = ?", (scan.rfid_tag,)).fetchone()
    if customer:
        return {"status": "success", "customer": dict(customer)}
    return {"status": "not_found", "message": "Unregistered Card"}

@app.post("/sessions/start")
def start_session(req: StartSessionRequest, db: sqlite3.Connection = Depends(get_db)):
    """Starts a new timer/session for a specific table."""
    cursor = db.cursor()

    table = cursor.execute("SELECT id, status FROM tables WHERE id = ?", (req.table_id,)).fetchone()
    if not table:
        raise HTTPException(status_code=404, detail=f"Table {req.table_id} not found")
    if table['status'] == 'ACTIVE':
        raise HTTPException(status_code=409, detail=f"Table {req.table_id} already has an active session")

    if req.customer_id is not None:
        customer = cursor.execute("SELECT id FROM customers WHERE id = ?", (req.customer_id,)).fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail=f"Customer {req.customer_id} not found")

    # Mark table as ACTIVE
    cursor.execute("UPDATE tables SET status = 'ACTIVE' WHERE id = ?", (req.table_id,))
    # Create the session
    cursor.execute('''
        INSERT INTO sessions (table_id, customer_id, start_time) 
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (req.table_id, req.customer_id))
    session_id = cursor.lastrowid
    db.commit()
    return {"status": "started", "session_id": session_id}

@app.post("/sessions/add_item")
def add_item(req: AddItemRequest, db: sqlite3.Connection = Depends(get_db)):
    """Adds a menu item (like Tea or Coffee) to an active session."""
    cursor = db.cursor()
    item = cursor.execute("SELECT name, price FROM menu_items WHERE id = ?", (req.item_id,)).fetchone()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    session = cursor.execute(
        "SELECT id, end_time FROM sessions WHERE id = ?", (req.session_id,)
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found")
    if session['end_time'] is not None:
        raise HTTPException(status_code=409, detail=f"Session {req.session_id} is already closed")

    # Log the item to the session
    cursor.execute('''
        INSERT INTO session_items (session_id, item_name, price) 
        VALUES (?, ?, ?)
    ''', (req.session_id, item['name'], item['price']))
    
    # Update the running items_cost in the sessions table
    cursor.execute('''
        UPDATE sessions SET items_cost = items_cost + ? WHERE id = ?
    ''', (item['price'], req.session_id))
    
    db.commit()
    return {"status": "item_added", "item": dict(item)}

@app.post("/sessions/checkout")
def checkout_session(req: CheckoutRequest, db: sqlite3.Connection = Depends(get_db)):
    """Closes the table, calculates the final bill, and logs debt if UNPAID."""
    if req.payment_status not in VALID_PAYMENT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"payment_status must be one of {', '.join(VALID_PAYMENT_STATUSES)}",
        )

    cursor = db.cursor()
    
    # Get session and table details to calculate time cost
    session = cursor.execute('''
        SELECT s.*, t.rate_per_minute 
        FROM sessions s 
        JOIN tables t ON s.table_id = t.id 
        WHERE s.id = ?
    ''', (req.session_id,)).fetchone()

    if not session:
        raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found")
    if session['end_time'] is not None:
        raise HTTPException(status_code=409, detail=f"Session {req.session_id} is already closed")

    time_cost = req.total_minutes * session['rate_per_minute']
    total_bill = time_cost + session['items_cost']

    # If unpaid and tied to a customer, add to their debt
    if req.payment_status == 'UNPAID' and session['customer_id']:
        cursor.execute('''
            UPDATE customers SET debt_amount = debt_amount + ? WHERE id = ?
        ''', (total_bill, session['customer_id']))

    # Finalize the session
    cursor.execute('''
        UPDATE sessions 
        SET end_time = CURRENT_TIMESTAMP, total_minutes = ?, time_cost = ?, total_bill = ?, payment_status = ? 
        WHERE id = ?
    ''', (req.total_minutes, time_cost, total_bill, req.payment_status, req.session_id))

    # Free up the table
    cursor.execute("UPDATE tables SET status = 'AVAILABLE' WHERE id = ?", (session['table_id'],))
    
    db.commit()
    return {"status": "closed", "final_bill": total_bill, "payment_status": req.payment_status}
