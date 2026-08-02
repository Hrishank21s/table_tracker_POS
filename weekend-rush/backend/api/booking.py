from flask import Blueprint, jsonify, request

from api import token_required
from models import Booking, TableData, db

booking_bp = Blueprint("booking", __name__)


@booking_bp.post("/request")
def request_booking():
    data = request.get_json(silent=True) or {}
    customer_name = (data.get("customer_name") or "").strip()
    upi_utr = (data.get("upi_utr") or "").strip()

    if not customer_name:
        return jsonify({"error": "Customer name is required"}), 400

    try:
        table_id = int(data.get("table_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Select a table to book"}), 400

    table = TableData.query.get(table_id)
    if table is None:
        return jsonify({"error": "Table not found"}), 404

    try:
        advance_amount = float(data.get("advance_amount"))
    except (TypeError, ValueError):
        return jsonify({"error": "Advance amount must be a number"}), 400
    if advance_amount <= 0:
        return jsonify({"error": "Advance amount must be greater than 0"}), 400

    if len(upi_utr) != 12 or not upi_utr.isalnum():
        return jsonify({"error": "UPI UTR must be exactly 12 alphanumeric characters"}), 400
    if Booking.query.filter_by(upi_utr=upi_utr).first():
        return jsonify({"error": "This UPI UTR has already been used"}), 409

    booking = Booking(
        table_id=table.id,
        customer_name=customer_name,
        advance_amount=advance_amount,
        upi_utr=upi_utr,
        status="pending",
    )
    if table.status == "idle":
        table.status = "booked"

    db.session.add(booking)
    db.session.commit()
    return jsonify({"message": "Booking request received", "booking": booking.to_dict()}), 201


@booking_bp.get("/")
@token_required
def list_bookings():
    rows = Booking.query.order_by(Booking.created_at.desc()).all()
    return jsonify({"bookings": [row.to_dict() for row in rows]}), 200


@booking_bp.post("/<int:booking_id>/confirm")
@token_required
def confirm_booking(booking_id):
    booking = Booking.query.get(booking_id)
    if booking is None:
        return jsonify({"error": "Booking not found"}), 404
    booking.status = "confirmed"
    db.session.commit()
    return jsonify({"message": "Booking confirmed", "booking": booking.to_dict()}), 200
