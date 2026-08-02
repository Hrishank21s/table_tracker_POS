import os
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from init_db import setup_database  # noqa: E402
from main import app, get_db  # noqa: E402


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Builds a fresh database in an isolated directory."""
    monkeypatch.chdir(tmp_path)
    setup_database()
    return tmp_path / "tracker.db"


@pytest.fixture
def db(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def customer(db):
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO customers (name, phone, rfid_tag, debt_amount) VALUES (?, ?, ?, ?)",
        ("Ravi", "9990001111", "TAG-001", 0.0),
    )
    db.commit()
    return cursor.lastrowid
