from flask import Blueprint, jsonify, request

from api import token_required
from models import Customer, db

customers_bp = Blueprint("customers", __name__)


@customers_bp.get("/")
@token_required
def list_customers():
    rows = Customer.query.order_by(Customer.name).all()
    return jsonify({"customers": [row.to_dict() for row in rows]}), 200


@customers_bp.post("/")
@token_required
def create_customer():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    nfc_uid = (data.get("nfc_uid") or "").strip() or None

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not phone.isdigit() or len(phone) < 10:
        return jsonify({"error": "Phone must be at least 10 digits"}), 400
    if Customer.query.filter_by(phone=phone).first():
        return jsonify({"error": "Phone already registered"}), 409
    if nfc_uid and Customer.query.filter_by(nfc_uid=nfc_uid).first():
        return jsonify({"error": "NFC UID already assigned"}), 409

    customer = Customer(
        name=name,
        phone=phone,
        is_member=bool(data.get("is_member", False)),
        nfc_uid=nfc_uid,
    )
    db.session.add(customer)
    db.session.commit()
    return jsonify({"message": "Customer added", "customer": customer.to_dict()}), 201


@customers_bp.put("/<int:customer_id>")
@token_required
def update_customer(customer_id):
    customer = Customer.query.get(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404

    data = request.get_json(silent=True) or {}
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Name cannot be empty"}), 400
        customer.name = name
    if "phone" in data:
        phone = (data.get("phone") or "").strip()
        if not phone.isdigit() or len(phone) < 10:
            return jsonify({"error": "Phone must be at least 10 digits"}), 400
        existing = Customer.query.filter_by(phone=phone).first()
        if existing and existing.id != customer.id:
            return jsonify({"error": "Phone already registered"}), 409
        customer.phone = phone
    if "is_member" in data:
        customer.is_member = bool(data.get("is_member"))
    if "nfc_uid" in data:
        nfc_uid = (data.get("nfc_uid") or "").strip() or None
        if nfc_uid:
            existing = Customer.query.filter_by(nfc_uid=nfc_uid).first()
            if existing and existing.id != customer.id:
                return jsonify({"error": "NFC UID already assigned"}), 409
        customer.nfc_uid = nfc_uid

    db.session.commit()
    return jsonify({"message": "Customer updated", "customer": customer.to_dict()}), 200


@customers_bp.post("/<int:customer_id>/toggle-member")
@token_required
def toggle_member(customer_id):
    customer = Customer.query.get(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404
    customer.is_member = not customer.is_member
    db.session.commit()
    return jsonify({"message": "Membership updated", "customer": customer.to_dict()}), 200


@customers_bp.post("/<int:customer_id>/nfc")
@token_required
def update_nfc(customer_id):
    customer = Customer.query.get(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404

    data = request.get_json(silent=True) or {}
    nfc_uid = (data.get("nfc_uid") or "").strip() or None
    if nfc_uid:
        existing = Customer.query.filter_by(nfc_uid=nfc_uid).first()
        if existing and existing.id != customer.id:
            return jsonify({"error": "NFC UID already assigned"}), 409
    customer.nfc_uid = nfc_uid
    db.session.commit()
    return jsonify({"message": "NFC UID updated", "customer": customer.to_dict()}), 200


@customers_bp.delete("/<int:customer_id>")
@token_required
def delete_customer(customer_id):
    customer = Customer.query.get(customer_id)
    if customer is None:
        return jsonify({"error": "Customer not found"}), 404
    db.session.delete(customer)
    db.session.commit()
    return jsonify({"message": "Customer removed"}), 200
