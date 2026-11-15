import re
from flask import Blueprint, g, jsonify, request

from backend.audit import log_admin_action
from backend.auth import (
    admin_required,
    create_access_token,
    hash_password,
    super_admin_required,
    verify_password,
)
from database.connector import get_cursor

ALLOWED_EMAIL_DOMAINS = ("@metlink.rw", "@metlink.com")
ALLOWED_ROLES = ("super_admin", "admin", "market_analyst")
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{3,50}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

auth_bp = Blueprint("auth", __name__, url_prefix="/api")


# ----------------------------------------------------------------------------
# Authentication Routes (/api/auth/...)
# ----------------------------------------------------------------------------

@auth_bp.post("/auth/login")
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


@auth_bp.post("/auth/logout")
@admin_required
def logout():
    # JWT tokens are stateless; the frontend clears the stored token on logout.
    return jsonify({"message": "Logged out successfully."}), 200


@auth_bp.get("/auth/me")
@admin_required
def get_me():
    return jsonify({"admin": g.current_admin}), 200


@auth_bp.post("/auth/change-password")
@admin_required
def change_password():
    """Change the authenticated admin's password with validation and audit logging."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not isinstance(current_password, str) or not isinstance(new_password, str) or not current_password or not new_password:
        return jsonify({"error": "Current password and new password are required non-empty strings."}), 400

    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters long."}), 400

    if len(new_password.encode("utf-8")) > 72:
        return jsonify({"error": "New password must not exceed 72 bytes."}), 400

    if new_password == current_password:
        return jsonify({"error": "New password must differ from current password."}), 400

    admin_id = g.current_admin["admin_id"]

    with get_cursor() as cur:
        cur.execute("SELECT password_hash FROM admins WHERE admin_id = %s;", (admin_id,))
        admin = cur.fetchone()

        if not admin or not verify_password(current_password, admin["password_hash"]):
            return jsonify({"error": "Current password is incorrect."}), 401

        new_hash = hash_password(new_password)
        cur.execute(
            """
            UPDATE admins
            SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
            WHERE admin_id = %s;
            """,
            (new_hash, admin_id),
        )
        log_admin_action(
            cur=cur,
            admin_id=admin_id,
            action="UPDATE",
            entity="admins",
            record_id=admin_id,
            details="Changed account password.",
        )

    return jsonify({"message": "Password updated successfully."}), 200


# ----------------------------------------------------------------------------
# Administrator Management Routes (/api/admins/...)
# Protected by @admin_required then @super_admin_required
# ----------------------------------------------------------------------------

@auth_bp.get("/admins")
@admin_required
@super_admin_required
def list_admins():
    """List all administrators ordered by created_at DESC. Never returns password_hash."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT admin_id, username, full_name, email, role, is_active, created_at
            FROM admins
            ORDER BY created_at DESC;
            """
        )
        admins = cur.fetchall()

    return jsonify({"admins": admins}), 200


@auth_bp.post("/admins")
@admin_required
@super_admin_required
def create_admin():
    """Create a new administrator with validation and audit logging."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    raw_username = data.get("username")
    raw_full_name = data.get("full_name")
    raw_email = data.get("email")
    raw_role = data.get("role")
    raw_password = data.get("temporary_password") if "temporary_password" in data else data.get("password")

    # 1. Body is a JSON object, every field is a non-empty string after trim
    if not isinstance(raw_username, str) or not isinstance(raw_full_name, str) or \
       not isinstance(raw_email, str) or not isinstance(raw_role, str) or \
       not isinstance(raw_password, str) or \
       not raw_username.strip() or not raw_full_name.strip() or \
       not raw_email.strip() or not raw_role.strip() or \
       not raw_password.strip():
        return jsonify({
            "error": "All fields (username, full_name, email, role, temporary_password) must be non-empty strings."
        }), 400

    username = raw_username.strip()
    full_name = raw_full_name.strip()
    email = raw_email.strip().lower()
    role = raw_role.strip()
    temporary_password = raw_password.strip()

    # 2. Username 3 to 50 chars, letters, digits, dot, underscore, hyphen only, stored lowercase
    if not USERNAME_PATTERN.match(username):
        return jsonify({
            "error": "Username must be 3 to 50 characters long and contain only letters, digits, dots, underscores, or hyphens."
        }), 400
    username = username.lower()

    # 3. Email lowercase, basic email format, domain must be @metlink.rw or @metlink.com
    if not EMAIL_PATTERN.match(email) or len(email) > 100:
        return jsonify({"error": "Invalid email format."}), 400

    if not any(email.endswith(domain) for domain in ALLOWED_EMAIL_DOMAINS):
        return jsonify({
            "error": f"Email domain must be one of: {', '.join(ALLOWED_EMAIL_DOMAINS)}."
        }), 400

    # 4. Role is one of super_admin, admin, market_analyst
    if role not in ALLOWED_ROLES:
        return jsonify({
            "error": f"Role must be one of: {', '.join(ALLOWED_ROLES)}."
        }), 400

    # 5. Temporary password at least 8 characters and at most 72 bytes in UTF-8
    if len(temporary_password) < 8:
        return jsonify({"error": "Temporary password must be at least 8 characters long."}), 400

    if len(temporary_password.encode("utf-8")) > 72:
        return jsonify({"error": "Temporary password must not exceed 72 bytes."}), 400

    current_admin_id = g.current_admin["admin_id"]

    # 6. Duplicate username or email returns 409
    with get_cursor() as cur:
        cur.execute(
            "SELECT username, email FROM admins WHERE username = %s OR email = %s;",
            (username, email),
        )
        existing = cur.fetchone()
        if existing:
            if existing["username"] == username:
                return jsonify({"error": f"An admin with username '{username}' already exists."}), 409
            return jsonify({"error": f"An admin with email '{email}' already exists."}), 409

        hashed = hash_password(temporary_password)

        cur.execute(
            """
            INSERT INTO admins (username, password_hash, full_name, email, role, is_active)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            RETURNING admin_id, username, full_name, email, role, is_active, created_at;
            """,
            (username, hashed, full_name, email, role),
        )
        new_admin = cur.fetchone()

        log_admin_action(
            cur=cur,
            admin_id=current_admin_id,
            action="CREATE",
            entity="admins",
            record_id=new_admin["admin_id"],
            details=f"Created admin {username} with role {role}.",
            new_value=dict(new_admin),
        )

    return jsonify({"admin": new_admin}), 201


@auth_bp.put("/admins/<int:admin_id>")
@admin_required
@super_admin_required
def update_admin(admin_id: int):
    """Update administrator details (full_name, role, is_active) with safety guards."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    full_name_raw = data.get("full_name")
    role_raw = data.get("role")
    is_active = data.get("is_active")

    if not isinstance(full_name_raw, str) or not full_name_raw.strip():
        return jsonify({"error": "Full name is required and must be a non-empty string."}), 400
    full_name = full_name_raw.strip()

    if not isinstance(role_raw, str) or role_raw.strip() not in ALLOWED_ROLES:
        return jsonify({"error": f"Role must be one of: {', '.join(ALLOWED_ROLES)}."}), 400
    role = role_raw.strip()

    if not isinstance(is_active, bool):
        return jsonify({"error": "is_active must be a boolean."}), 400

    current_admin_id = g.current_admin["admin_id"]

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT admin_id, username, full_name, email, role, is_active, created_at
            FROM admins
            WHERE admin_id = %s;
            """,
            (admin_id,),
        )
        existing = cur.fetchone()
        if not existing:
            return jsonify({"error": "Admin not found."}), 404

        # Guard a: You cannot change your own role or deactivate your own account
        if admin_id == current_admin_id:
            if is_active is False:
                return jsonify({"error": "You cannot deactivate your own admin account."}), 400
            if role != existing["role"]:
                return jsonify({"error": "You cannot change your own role."}), 400

        # Guard b: You cannot demote or deactivate the last active super_admin
        target_was_active_super_admin = (existing["role"] == "super_admin" and existing["is_active"] is True)
        target_will_be_active_super_admin = (role == "super_admin" and is_active is True)
        if target_was_active_super_admin and not target_will_be_active_super_admin:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM admins
                WHERE role = 'super_admin' AND is_active = TRUE AND admin_id != %s;
                """,
                (admin_id,),
            )
            remaining_active_super_admins = cur.fetchone()["total"]
            if remaining_active_super_admins == 0:
                return jsonify({"error": "Cannot demote or deactivate the last active super admin."}), 400

        # Audit action and description
        if existing["is_active"] is True and is_active is False:
            action = "DEACTIVATE"
            details = f"Deactivated admin {existing['username']}."
        elif existing["is_active"] is False and is_active is True:
            action = "UPDATE"
            details = f"Reactivated admin {existing['username']}."
        else:
            action = "UPDATE"
            details = f"Updated admin {existing['username']}."

        cur.execute(
            """
            UPDATE admins
            SET full_name = %s, role = %s, is_active = %s, updated_at = CURRENT_TIMESTAMP
            WHERE admin_id = %s
            RETURNING admin_id, username, full_name, email, role, is_active, created_at, updated_at;
            """,
            (full_name, role, is_active, admin_id),
        )
        updated_admin = cur.fetchone()

        log_admin_action(
            cur=cur,
            admin_id=current_admin_id,
            action=action,
            entity="admins",
            record_id=admin_id,
            details=details,
            old_value=dict(existing),
            new_value=dict(updated_admin),
        )

    return jsonify({"admin": updated_admin}), 200
