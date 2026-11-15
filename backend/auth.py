import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from flask import g, jsonify, request

from database.connector import get_cursor

JWT_SECRET = os.getenv("JWT_SECRET", "metlink-change-this-secret-in-production")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 12


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plain-text password against a stored bcrypt hash."""
    if not plain_password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(admin: dict) -> str:
    """Generate a signed JWT token for an authenticated admin."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(admin["admin_id"]),
        "username": admin["username"],
        "role": admin["role"],
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload dict or None if invalid."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def admin_required(fn):
    """Route decorator that blocks unauthenticated or inactive admin requests."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authentication required."}), 401

        token = auth_header.split(" ", 1)[1].strip()
        payload = decode_access_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired session. Please log in again."}), 401

        admin_id = int(payload["sub"])
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT admin_id, username, full_name, email, role, is_active
                FROM admins
                WHERE admin_id = %s;
                """,
                (admin_id,),
            )
            admin = cur.fetchone()

        if not admin or not admin["is_active"]:
            return jsonify({"error": "Admin account not found or deactivated."}), 403

        g.current_admin = admin
        return fn(*args, **kwargs)

    return wrapper


def super_admin_required(fn):
    """
    Route decorator requiring an active super_admin session.
    Stackable under @admin_required.
    Loads role and is_active directly from the database (not from token).
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        admin = getattr(g, "current_admin", None)
        if not admin or "admin_id" not in admin:
            return jsonify({"error": "Authentication required."}), 401

        admin_id = admin["admin_id"]
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT role, is_active
                FROM admins
                WHERE admin_id = %s;
                """,
                (admin_id,),
            )
            admin_row = cur.fetchone()

        if not admin_row or admin_row["role"] != "super_admin" or not admin_row["is_active"]:
            return jsonify({"error": "Super admin access required."}), 403

        g.current_admin["role"] = admin_row["role"]
        g.current_admin["is_active"] = admin_row["is_active"]
        return fn(*args, **kwargs)

    return wrapper

