from db import connect


def setup_database(db_path=None):
    conn = connect(db_path)
    cursor = conn.cursor()

    # 1. Zones (Floors)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS zones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    ''')

    # 2. Tables (Dynamically assigned to zones, tracks rate and status)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zone_id INTEGER,
        table_name TEXT NOT NULL,
        rate_per_minute REAL DEFAULT 3.0,
        status TEXT DEFAULT 'AVAILABLE',
        FOREIGN KEY(zone_id) REFERENCES zones(id)
    )
    ''')

    # 3. Menu Items (Fixed prices for quick-add buttons)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS menu_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        variant TEXT, 
        price REAL NOT NULL
    )
    ''')

    # 4. Customers (Tracks RFID tags and unpaid tabs)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        rfid_tag TEXT UNIQUE,
        debt_amount REAL DEFAULT 0.0
    )
    ''')

    # 5. Sessions (The core tracker: handles the 3 checkout states)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_id INTEGER,
        customer_id INTEGER, 
        start_time TIMESTAMP NOT NULL,
        end_time TIMESTAMP,
        total_minutes INTEGER DEFAULT 0,
        time_cost REAL DEFAULT 0.0,
        items_cost REAL DEFAULT 0.0,
        total_bill REAL DEFAULT 0.0,
        payment_status TEXT, -- 'PAID', 'UNPAID', or 'CLOSE' (Anonymous)
        FOREIGN KEY(table_id) REFERENCES tables(id),
        FOREIGN KEY(customer_id) REFERENCES customers(id)
    )
    ''')

    # 6. Session Items (Logs exactly what was ordered during a session)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS session_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        item_name TEXT NOT NULL,
        price REAL NOT NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )
    ''')

    # --- INITIAL DATA POPULATION ---

    # Setup the 3 Zones
    zones_data = [('Zone 1 (Snooker)',), ('Zone 2 (Under Construction)',), ('Zone 3 (Pool)',)]
    cursor.executemany("INSERT OR IGNORE INTO zones (name) VALUES (?)", zones_data)

    # Setup Initial Tables (3 in Zone 1, 3 in Zone 3). Only seeded on a fresh
    # database so re-running this script never duplicates rows.
    if cursor.execute("SELECT COUNT(*) FROM tables").fetchone()[0] == 0:
        tables_data = [
            (1, 'Snooker 1'), (1, 'Snooker 2'), (1, 'Snooker 3'),
            (3, 'Pool 1'), (3, 'Pool 2'), (3, 'Pool 3')
        ]
        cursor.executemany("INSERT INTO tables (zone_id, table_name) VALUES (?, ?)", tables_data)

    # Setup Menu Items
    if cursor.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0] == 0:
        menu_data = [
            ('Tea', 'Half', 20.0), ('Tea', 'Full', 40.0),
            ('Coffee', 'Half', 30.0), ('Coffee', 'Full', 50.0)
        ]
        cursor.executemany("INSERT INTO menu_items (name, variant, price) VALUES (?, ?, ?)", menu_data)

    conn.commit()
    conn.close()

if __name__ == '__main__':
    setup_database()
    print("Database structure successfully built for multi-zone tracking and dual billing!")
