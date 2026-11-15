from flask import Blueprint, g, jsonify, request

from backend.auth import admin_required, create_access_token, verify_password
from database.connector import get_cursor

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT admin_id, username, password_hash, full_name, email, role, is_active
            FROM admins
            WHERE username = %s;
            """,
            (username,),
        )
        admin = cur.fetchone()

    if not admin or not verify_password(password, admin["password_hash"]):
        return jsonify({"error": "Invalid username or password."}), 401

    if not admin["is_active"]:
        return jsonify({"error": "This admin account has been deactivated."}), 403

    token = create_access_token(admin)
    return jsonify({
        "token": token,
        "admin": {
            "admin_id": admin["admin_id"],
            "username": admin["username"],
            "full_name": admin["full_name"],
            "email": admin["email"],
            "role": admin["role"],
        },
    }), 200


@auth_bp.post("/logout")
@admin_required
def logout():
    # JWT tokens are stateless; the frontend clears the stored token on logout.
    return jsonify({"message": "Logged out successfully."}), 200


@auth_bp.get("/me")
@admin_required
def get_me():
    return jsonify({"admin": g.current_admin}), 200
