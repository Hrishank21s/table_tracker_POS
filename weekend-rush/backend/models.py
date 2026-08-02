from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")

    def to_dict(self):
        return {"id": self.id, "username": self.username, "role": self.role}


class TableData(db.Model):
    __tablename__ = "tables"

    id = db.Column(db.Integer, primary_key=True)
    table_no = db.Column(db.Integer, nullable=False)
    floor = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(20), nullable=False, default="idle")
    current_rate = db.Column(db.Float, nullable=False, default=3.0)
    active_start = db.Column(db.DateTime, nullable=True)
    accumulated_seconds = db.Column(db.Integer, nullable=False, default=0)

    def elapsed_seconds(self, now=None):
        """Total billable seconds including the currently running segment."""
        total = self.accumulated_seconds or 0
        if self.active_start is not None:
            now = now or datetime.utcnow()
            total += max(0, int((now - self.active_start).total_seconds()))
        return total

    def to_dict(self):
        return {
            "id": self.id,
            "table_no": self.table_no,
            "floor": self.floor,
            "status": self.status,
            "current_rate": self.current_rate,
            "active_start": self.active_start.isoformat() + "Z" if self.active_start else None,
            "accumulated_seconds": self.accumulated_seconds,
            "elapsed_seconds": self.elapsed_seconds(),
            "server_time": datetime.utcnow().isoformat() + "Z",
        }


class SessionLog(db.Model):
    __tablename__ = "session_logs"

    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey("tables.id"), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    total_amount = db.Column(db.Float, nullable=False, default=0.0)
    split_ways = db.Column(db.Integer, nullable=False, default=1)

    def to_dict(self):
        return {
            "id": self.id,
            "table_id": self.table_id,
            "start_time": self.start_time.isoformat() + "Z",
            "end_time": self.end_time.isoformat() + "Z",
            "total_amount": self.total_amount,
            "split_ways": self.split_ways,
        }


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    is_member = db.Column(db.Boolean, nullable=False, default=False)
    nfc_uid = db.Column(db.String(64), unique=True, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "is_member": self.is_member,
            "nfc_uid": self.nfc_uid,
        }


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey("tables.id"), nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    advance_amount = db.Column(db.Float, nullable=False, default=0.0)
    upi_utr = db.Column(db.String(12), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "table_id": self.table_id,
            "customer_name": self.customer_name,
            "advance_amount": self.advance_amount,
            "upi_utr": self.upi_utr,
            "status": self.status,
            "created_at": self.created_at.isoformat() + "Z",
        }
