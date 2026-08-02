from flask import Blueprint, jsonify, request

from api import admin_required, token_required
from models import Booking, SessionLog, TableData, User, db

settings_bp = Blueprint("settings", __name__)

VALID_FLOORS = (1, 2, 3)


@settings_bp.get("/tables")
@token_required
def list_tables():
    rows = TableData.query.order_by(TableData.floor, TableData.table_no).all()
    return jsonify({"tables": [row.to_dict() for row in rows]}), 200


@settings_bp.post("/tables")
@admin_required
def add_table():
    data = request.get_json(silent=True) or {}
    try:
        table_no = int(data.get("table_no"))
        floor = int(data.get("floor"))
        current_rate = float(data.get("current_rate", 3.0))
    except (TypeError, ValueError):
        return jsonify({"error": "table_no, floor and current_rate must be numeric"}), 400

    if floor not in VALID_FLOORS:
        return jsonify({"error": "Floor must be 1, 2 or 3"}), 400
    if current_rate <= 0:
        return jsonify({"error": "Rate must be greater than zero"}), 400
    if TableData.query.filter_by(table_no=table_no, floor=floor).first():
        return jsonify({"error": "Table number already exists on this floor"}), 409

    table = TableData(table_no=table_no, floor=floor, status="idle", current_rate=current_rate)
    db.session.add(table)
    db.session.commit()
    return jsonify({"message": "Table added", "table": table.to_dict()}), 201


@settings_bp.put("/tables/<int:table_id>")
@admin_required
def update_table(table_id):
    table = TableData.query.get(table_id)
    if table is None:
        return jsonify({"error": "Table not found"}), 404

    data = request.get_json(silent=True) or {}
    if "floor" in data:
        try:
            floor = int(data.get("floor"))
        except (TypeError, ValueError):
            return jsonify({"error": "Floor must be numeric"}), 400
        if floor not in VALID_FLOORS:
            return jsonify({"error": "Floor must be 1, 2 or 3"}), 400
        table.floor = floor
    if "table_no" in data:
        try:
            table.table_no = int(data.get("table_no"))
        except (TypeError, ValueError):
            return jsonify({"error": "Table number must be numeric"}), 400
    if "current_rate" in data:
        try:
            rate = float(data.get("current_rate"))
        except (TypeError, ValueError):
            return jsonify({"error": "Rate must be numeric"}), 400
        if rate <= 0:
            return jsonify({"error": "Rate must be greater than zero"}), 400
        table.current_rate = rate

    db.session.commit()
    return jsonify({"message": "Table updated", "table": table.to_dict()}), 200


@settings_bp.delete("/tables/<int:table_id>")
@admin_required
def delete_table(table_id):
    table = TableData.query.get(table_id)
    if table is None:
        return jsonify({"error": "Table not found"}), 404
    if table.status in ("running", "paused"):
        return jsonify({"error": "Stop the running session before removing this table"}), 400

    SessionLog.query.filter_by(table_id=table.id).delete()
    Booking.query.filter_by(table_id=table.id).delete()
    db.session.delete(table)
    db.session.commit()
    return jsonify({"message": "Table removed"}), 200


@settings_bp.get("/users")
@admin_required
def list_users():
    rows = User.query.order_by(User.username).all()
    return jsonify({"users": [row.to_dict() for row in rows]}), 200


@settings_bp.post("/users")
@admin_required
def add_user():
    from app import bcrypt

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "staff").strip()

    if not username:
        return jsonify({"error": "Username is required"}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400
    if role not in ("admin", "staff"):
        return jsonify({"error": "Role must be admin or staff"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    user = User(
        username=username,
        password_hash=bcrypt.generate_password_hash(password).decode("utf-8"),
        role=role,
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User added", "user": user.to_dict()}), 201


@settings_bp.put("/users/<int:user_id>")
@admin_required
def update_user(user_id):
    from app import bcrypt

    user = User.query.get(user_id)
    if user is None:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    if "role" in data:
        role = (data.get("role") or "").strip()
        if role not in ("admin", "staff"):
            return jsonify({"error": "Role must be admin or staff"}), 400
        user.role = role
    if data.get("password"):
        password = data.get("password")
        if len(password) < 4:
            return jsonify({"error": "Password must be at least 4 characters"}), 400
        user.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    db.session.commit()
    return jsonify({"message": "User updated", "user": user.to_dict()}), 200


@settings_bp.delete("/users/<int:user_id>")
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    if user.id == request.current_user.id:
        return jsonify({"error": "You cannot delete your own account"}), 400
    if user.role == "admin" and User.query.filter_by(role="admin").count() <= 1:
        return jsonify({"error": "At least one admin must remain"}), 400

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User removed"}), 200
