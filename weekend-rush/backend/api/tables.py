from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from api import token_required
from models import SessionLog, TableData, db

tables_bp = Blueprint("tables", __name__)


def _grouped_payload():
    floors = {}
    for table in TableData.query.order_by(TableData.floor, TableData.table_no).all():
        floors.setdefault(str(table.floor), []).append(table.to_dict())
    return {"floors": floors, "server_time": datetime.utcnow().isoformat() + "Z"}


@tables_bp.get("/")
def list_tables():
    return jsonify(_grouped_payload()), 200


@tables_bp.get("/<int:table_id>")
def get_table(table_id):
    table = TableData.query.get(table_id)
    if table is None:
        return jsonify({"error": "Table not found"}), 404
    return jsonify(table.to_dict()), 200


@tables_bp.post("/<int:table_id>/play")
@token_required
def play(table_id):
    table = TableData.query.get(table_id)
    if table is None:
        return jsonify({"error": "Table not found"}), 404
    if table.status == "running":
        return jsonify({"error": "Table is already running"}), 400

    table.active_start = datetime.utcnow()
    table.status = "running"
    db.session.commit()
    return jsonify({"message": "Table started", "table": table.to_dict()}), 200


@tables_bp.post("/<int:table_id>/pause")
@token_required
def pause(table_id):
    table = TableData.query.get(table_id)
    if table is None:
        return jsonify({"error": "Table not found"}), 404
    if table.status != "running" or table.active_start is None:
        return jsonify({"error": "Table is not running"}), 400

    elapsed = int((datetime.utcnow() - table.active_start).total_seconds())
    table.accumulated_seconds = (table.accumulated_seconds or 0) + max(0, elapsed)
    table.active_start = None
    table.status = "paused"
    db.session.commit()
    return jsonify({"message": "Table paused", "table": table.to_dict()}), 200


@tables_bp.post("/<int:table_id>/stop")
@token_required
def stop(table_id):
    table = TableData.query.get(table_id)
    if table is None:
        return jsonify({"error": "Table not found"}), 404
    if table.status not in ("running", "paused"):
        return jsonify({"error": "Table has no active session"}), 400

    data = request.get_json(silent=True) or {}
    try:
        split_ways = int(data.get("split_ways", 1) or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "split_ways must be a whole number"}), 400
    if split_ways < 1:
        return jsonify({"error": "split_ways must be at least 1"}), 400

    now = datetime.utcnow()
    total_seconds = table.elapsed_seconds(now)
    amount = round((total_seconds / 3600.0) * table.current_rate, 2)
    split_amount = round(amount / split_ways, 2)

    log = SessionLog(
        table_id=table.id,
        start_time=now - timedelta(seconds=total_seconds),
        end_time=now,
        total_amount=amount,
        split_ways=split_ways,
    )
    db.session.add(log)

    table.status = "idle"
    table.active_start = None
    table.accumulated_seconds = 0
    db.session.commit()

    return (
        jsonify(
            {
                "message": "Session closed",
                "currency": "INR",
                "total_seconds": total_seconds,
                "total_amount": amount,
                "split_ways": split_ways,
                "split_amount": split_amount,
                "session_log": log.to_dict(),
                "table": table.to_dict(),
            }
        ),
        200,
    )


@tables_bp.get("/logs")
@token_required
def logs():
    entries = SessionLog.query.order_by(SessionLog.end_time.desc()).limit(100).all()
    return jsonify({"logs": [entry.to_dict() for entry in entries]}), 200
