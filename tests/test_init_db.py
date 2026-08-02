import sqlite3

from init_db import setup_database

EXPECTED_TABLES = {
    "zones",
    "tables",
    "menu_items",
    "customers",
    "sessions",
    "session_items",
}


def test_creates_all_tables(db):
    names = {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert EXPECTED_TABLES <= names


def test_seeds_zones(db):
    zones = [row["name"] for row in db.execute("SELECT name FROM zones ORDER BY id")]
    assert zones == [
        "Zone 1 (Snooker)",
        "Zone 2 (Under Construction)",
        "Zone 3 (Pool)",
    ]


def test_seeds_tables_into_snooker_and_pool_zones(db):
    rows = db.execute("SELECT zone_id, table_name FROM tables ORDER BY id").fetchall()
    assert [(r["zone_id"], r["table_name"]) for r in rows] == [
        (1, "Snooker 1"),
        (1, "Snooker 2"),
        (1, "Snooker 3"),
        (3, "Pool 1"),
        (3, "Pool 2"),
        (3, "Pool 3"),
    ]


def test_tables_have_default_rate_and_status(db):
    row = db.execute("SELECT rate_per_minute, status FROM tables WHERE id = 1").fetchone()
    assert row["rate_per_minute"] == 3.0
    assert row["status"] == "AVAILABLE"


def test_seeds_menu_items(db):
    rows = db.execute("SELECT name, variant, price FROM menu_items ORDER BY id").fetchall()
    assert [(r["name"], r["variant"], r["price"]) for r in rows] == [
        ("Tea", "Half", 20.0),
        ("Tea", "Full", 40.0),
        ("Coffee", "Half", 30.0),
        ("Coffee", "Full", 50.0),
    ]


def test_session_numeric_columns_default_to_zero(db):
    db.execute("INSERT INTO sessions (table_id, start_time) VALUES (1, CURRENT_TIMESTAMP)")
    db.commit()
    row = db.execute("SELECT * FROM sessions WHERE id = 1").fetchone()
    assert (row["total_minutes"], row["time_cost"], row["items_cost"], row["total_bill"]) == (
        0,
        0.0,
        0.0,
        0.0,
    )
    assert row["end_time"] is None
    assert row["payment_status"] is None


def test_customer_debt_defaults_to_zero(db):
    db.execute("INSERT INTO customers (name) VALUES ('Anon')")
    db.commit()
    assert db.execute("SELECT debt_amount FROM customers WHERE id = 1").fetchone()[0] == 0.0


def test_rfid_tag_is_unique(db, customer):
    try:
        db.execute("INSERT INTO customers (name, rfid_tag) VALUES ('Clone', 'TAG-001')")
        raise AssertionError("duplicate rfid_tag should be rejected")
    except sqlite3.IntegrityError:
        pass


def test_rerunning_setup_does_not_duplicate_seed_data(db_path, db):
    setup_database(str(db_path))
    setup_database(str(db_path))
    counts = {
        name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        for name in ("zones", "tables", "menu_items")
    }
    assert counts == {"zones": 3, "tables": 6, "menu_items": 4}


def test_rerunning_setup_preserves_existing_rows(db_path, db):
    db.execute("UPDATE tables SET rate_per_minute = 7.0 WHERE id = 1")
    db.commit()

    setup_database(str(db_path))

    assert db.execute("SELECT rate_per_minute FROM tables WHERE id = 1").fetchone()[0] == 7.0


def test_setup_creates_database_at_given_path(tmp_path):
    target = tmp_path / "nested" / "custom.db"
    target.parent.mkdir()

    setup_database(str(target))

    assert target.exists()
    conn = sqlite3.connect(target)
    assert conn.execute("SELECT COUNT(*) FROM tables").fetchone()[0] == 6
    conn.close()
