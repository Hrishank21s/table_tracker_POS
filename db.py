import sqlite3

DB_PATH = 'tracker.db'


def connect():
    """Opens a connection to the tracker database with dict-like rows."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows):
    return [dict(row) for row in rows]
