from flask import Blueprint, jsonify, request

from api import generate_token, token_required
from models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    from app import bcrypt

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if user is None or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid username or password"}), 401

    return jsonify({"token": generate_token(user), "user": user.to_dict()}), 200


@auth_bp.get("/me")
@token_required
def me():
    return jsonify(request.current_user.to_dict()), 200
