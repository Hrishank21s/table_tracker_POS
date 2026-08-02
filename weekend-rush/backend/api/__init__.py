from functools import wraps

import jwt
from flask import current_app, jsonify, request

from models import User


def generate_token(user):
    from datetime import datetime, timedelta

    payload = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(hours=12),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def decode_token(token):
    return jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])


def _current_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None, "Missing bearer token"
    token = header.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        return None, "Token expired"
    except jwt.InvalidTokenError:
        return None, "Invalid token"
    user = User.query.get(payload.get("user_id"))
    if user is None:
        return None, "User no longer exists"
    return user, None


def token_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, error = _current_user()
        if user is None:
            return jsonify({"error": error}), 401
        request.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user, error = _current_user()
        if user is None:
            return jsonify({"error": error}), 401
        if user.role != "admin":
            return jsonify({"error": "Admin role required"}), 403
        request.current_user = user
        return fn(*args, **kwargs)

    return wrapper
