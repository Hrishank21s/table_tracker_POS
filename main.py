from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
import os
import sqlite3
from typing import Optional

from init_db import setup_database

DB_PATH = os.environ.get("TRACKER_DB", "tracker.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Creates and seeds the database on boot so the API works out of the box."""
    setup_database(DB_PATH)
    yield


app = FastAPI(title="Weekend Rush Table Tracker API", lifespan=lifespan)

# Allow your HTML frontend to talk to this server without security blocks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper function to get database connection
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Returns rows as dictionaries
    try:
        yield conn
    finally:
        conn.close()

# --- Pydantic Models for incoming JSON requests ---
class ScanRequest(BaseModel):
    rfid_tag: str

class StartSessionRequest(BaseModel):
    table_id: int
    customer_id: Optional[int] = None
    rate_per_minute: Optional[float] = None

class AddItemRequest(BaseModel):
    session_id: int
    item_id: int

class CheckoutRequest(BaseModel):
    session_id: int
    payment_status: str # 'PAID', 'UNPAID', or 'CLOSE'
    total_minutes: float

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
    table = cursor.execute("SELECT id FROM tables WHERE id = ?", (req.table_id,)).fetchone()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    if req.rate_per_minute is not None:
        cursor.execute(
            "UPDATE tables SET rate_per_minute = ? WHERE id = ?",
            (req.rate_per_minute, req.table_id),
        )

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

    session = cursor.execute("SELECT id FROM sessions WHERE id = ?", (req.session_id,)).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
    cursor = db.cursor()
    
    # Get session and table details to calculate time cost
    session = cursor.execute('''
        SELECT s.*, t.rate_per_minute 
        FROM sessions s 
        JOIN tables t ON s.table_id = t.id 
        WHERE s.id = ?
    ''', (req.session_id,)).fetchone()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
