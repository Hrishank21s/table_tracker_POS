import sqlite3

from fastapi.testclient import TestClient

import main


def start_session(client, table_id=1, customer_id=None, rate_per_minute=None):
    payload = {
        "table_id": table_id,
        "customer_id": customer_id,
        "rate_per_minute": rate_per_minute,
    }
    return client.post("/sessions/start", json=payload).json()["session_id"]


def test_read_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "Server is running offline and ready."}


def test_get_zones_groups_tables_by_zone(client):
    response = client.get("/zones")
    assert response.status_code == 200
    zones = response.json()
    assert [z["zone_name"] for z in zones] == [
        "Zone 1 (Snooker)",
        "Zone 2 (Under Construction)",
        "Zone 3 (Pool)",
    ]
    assert [t["table_name"] for t in zones[0]["tables"]] == [
        "Snooker 1",
        "Snooker 2",
        "Snooker 3",
    ]
    assert zones[1]["tables"] == []


def test_get_menu(client):
    items = client.get("/menu").json()
    assert len(items) == 4
    assert {"id", "name", "variant", "price"} == set(items[0])
    assert items[0]["name"] == "Tea"


def test_scan_known_card(client, customer):
    response = client.post("/api/scan", json={"rfid_tag": "TAG-001"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["customer"]["id"] == customer
    assert body["customer"]["name"] == "Ravi"


def test_scan_unknown_card(client):
    body = client.post("/api/scan", json={"rfid_tag": "NOPE"}).json()
    assert body == {"status": "not_found", "message": "Unregistered Card"}


def test_scan_requires_rfid_tag(client):
    assert client.post("/api/scan", json={}).status_code == 422


def test_start_session_marks_table_active(client, db):
    body = client.post("/sessions/start", json={"table_id": 1}).json()
    assert body["status"] == "started"

    session = db.execute("SELECT * FROM sessions WHERE id = ?", (body["session_id"],)).fetchone()
    assert session["table_id"] == 1
    assert session["customer_id"] is None
    assert session["start_time"] is not None
    assert db.execute("SELECT status FROM tables WHERE id = 1").fetchone()[0] == "ACTIVE"


def test_start_session_links_customer(client, db, customer):
    session_id = start_session(client, customer_id=customer)
    row = db.execute("SELECT customer_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
    assert row["customer_id"] == customer


def test_add_item_logs_item_and_accumulates_cost(client, db):
    session_id = start_session(client)

    body = client.post("/sessions/add_item", json={"session_id": session_id, "item_id": 1}).json()
    assert body == {"status": "item_added", "item": {"name": "Tea", "price": 20.0}}

    client.post("/sessions/add_item", json={"session_id": session_id, "item_id": 4})

    logged = db.execute(
        "SELECT item_name, price FROM session_items WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    assert [(r["item_name"], r["price"]) for r in logged] == [("Tea", 20.0), ("Coffee", 50.0)]
    assert db.execute(
        "SELECT items_cost FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()[0] == 70.0


def test_start_session_unknown_table(client, db):
    response = client.post("/sessions/start", json={"table_id": 999})
    assert response.status_code == 404
    assert response.json()["detail"] == "Table not found"
    assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_start_session_updates_table_rate(client, db):
    start_session(client, rate_per_minute=4.5)
    assert db.execute("SELECT rate_per_minute FROM tables WHERE id = 1").fetchone()[0] == 4.5


def test_start_session_keeps_rate_when_not_supplied(client, db):
    db.execute("UPDATE tables SET rate_per_minute = 6.0 WHERE id = 1")
    db.commit()
    start_session(client)
    assert db.execute("SELECT rate_per_minute FROM tables WHERE id = 1").fetchone()[0] == 6.0


def test_add_item_unknown_session(client, db):
    response = client.post("/sessions/add_item", json={"session_id": 999, "item_id": 1})
    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"
    assert db.execute("SELECT COUNT(*) FROM session_items").fetchone()[0] == 0


def test_add_item_unknown_item(client, db):
    session_id = start_session(client)
    response = client.post("/sessions/add_item", json={"session_id": session_id, "item_id": 999})
    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"
    assert db.execute("SELECT COUNT(*) FROM session_items").fetchone()[0] == 0


def test_checkout_paid_session(client, db):
    session_id = start_session(client)
    client.post("/sessions/add_item", json={"session_id": session_id, "item_id": 1})

    body = client.post(
        "/sessions/checkout",
        json={"session_id": session_id, "payment_status": "PAID", "total_minutes": 10},
    ).json()
    assert body == {"status": "closed", "final_bill": 50.0, "payment_status": "PAID"}

    session = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    assert session["time_cost"] == 30.0
    assert session["total_bill"] == 50.0
    assert session["total_minutes"] == 10
    assert session["payment_status"] == "PAID"
    assert session["end_time"] is not None
    assert db.execute("SELECT status FROM tables WHERE id = 1").fetchone()[0] == "AVAILABLE"


def test_checkout_unpaid_adds_debt_to_customer(client, db, customer):
    session_id = start_session(client, customer_id=customer)
    client.post("/sessions/add_item", json={"session_id": session_id, "item_id": 2})

    body = client.post(
        "/sessions/checkout",
        json={"session_id": session_id, "payment_status": "UNPAID", "total_minutes": 20},
    ).json()
    assert body["final_bill"] == 100.0
    assert db.execute(
        "SELECT debt_amount FROM customers WHERE id = ?", (customer,)
    ).fetchone()[0] == 100.0


def test_checkout_unpaid_without_customer_records_no_debt(client, db):
    session_id = start_session(client)
    client.post(
        "/sessions/checkout",
        json={"session_id": session_id, "payment_status": "UNPAID", "total_minutes": 5},
    )
    assert db.execute("SELECT COALESCE(SUM(debt_amount), 0) FROM customers").fetchone()[0] == 0


def test_checkout_close_does_not_touch_debt(client, db, customer):
    session_id = start_session(client, customer_id=customer)
    client.post(
        "/sessions/checkout",
        json={"session_id": session_id, "payment_status": "CLOSE", "total_minutes": 15},
    )
    assert db.execute(
        "SELECT debt_amount FROM customers WHERE id = ?", (customer,)
    ).fetchone()[0] == 0.0
    assert db.execute(
        "SELECT payment_status FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()[0] == "CLOSE"


def test_checkout_uses_table_specific_rate(client, db):
    db.execute("UPDATE tables SET rate_per_minute = 5.5 WHERE id = 4")
    db.commit()
    session_id = start_session(client, table_id=4)

    body = client.post(
        "/sessions/checkout",
        json={"session_id": session_id, "payment_status": "PAID", "total_minutes": 4},
    ).json()
    assert body["final_bill"] == 22.0


def test_checkout_unknown_session(client):
    response = client.post(
        "/sessions/checkout",
        json={"session_id": 999, "payment_status": "PAID", "total_minutes": 5},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_checkout_uses_rate_set_at_session_start(client):
    session_id = start_session(client, rate_per_minute=4.0)
    body = client.post(
        "/sessions/checkout",
        json={"session_id": session_id, "payment_status": "PAID", "total_minutes": 10},
    ).json()
    assert body["final_bill"] == 40.0


def test_checkout_requires_valid_payload(client):
    assert client.post("/sessions/checkout", json={"session_id": 1}).status_code == 422


def test_get_db_yields_row_connection_and_closes_it(db_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", str(db_path))
    generator = main.get_db()
    conn = next(generator)

    assert conn.row_factory is sqlite3.Row
    assert conn.execute("SELECT COUNT(*) FROM tables").fetchone()[0] == 6

    exhausted = object()
    assert next(generator, exhausted) is exhausted
    try:
        conn.execute("SELECT 1")
        raise AssertionError("connection should be closed")
    except sqlite3.ProgrammingError:
        pass


def test_startup_creates_and_seeds_database(tmp_path, monkeypatch):
    db_file = tmp_path / "boot.db"
    monkeypatch.setattr(main, "DB_PATH", str(db_file))

    with TestClient(main.app) as booted:
        assert len(booted.get("/menu").json()) == 4
    assert db_file.exists()


def test_cors_headers_allow_any_origin(client):
    response = client.get("/", headers={"Origin": "http://localhost:8080"})
    assert response.headers["access-control-allow-origin"] in ("*", "http://localhost:8080")
