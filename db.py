import os
import sqlite3

DEFAULT_DB_PATH = os.environ.get("TRACKER_DB", "tracker.db")


def connect(db_path=None):
    """Opens a connection to the tracker database with dict-like rows."""
    conn = sqlite3.connect(db_path or DEFAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows):
    return [dict(row) for row in rows]
