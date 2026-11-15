from flask import Blueprint, g, jsonify, request

from backend.audit import log_admin_action
from backend.auth import admin_required
from database.connector import get_cursor

admin_bp = Blueprint("admin", __name__, url_prefix="/api")


# ----------------------------------------------------------------------------
# 1. Public Landing Page Endpoint (Live Kigali Market Prices)
# ----------------------------------------------------------------------------
@admin_bp.get("/public/markets")
def list_public_markets():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT market_id, market_name, location, average_price_per_kg, demand_level, created_at
            FROM market_information
            WHERE is_active = TRUE
            ORDER BY created_at DESC;
            """
        )
        markets = cur.fetchall()
    return jsonify({"markets": markets}), 200


# ----------------------------------------------------------------------------
# 2. Dashboard Summary KPIs & Recent Activity
# ----------------------------------------------------------------------------
@admin_bp.get("/dashboard/summary")
@admin_required
def dashboard_summary():
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM farmers WHERE is_active = TRUE;")
        active_farmers = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM harvest_submissions;")
        total_submissions = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM harvest_submissions WHERE status = 'PENDING';")
        pending_submissions = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM sms_logs WHERE status = 'DELIVERED';")
        delivered_sms = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS total FROM sms_logs;")
        total_sms = cur.fetchone()["total"]

        cur.execute(
            """
            SELECT season_id, season_name, start_date, end_date, description
            FROM seasonal_information
            WHERE is_active = TRUE
            ORDER BY start_date DESC
            LIMIT 1;
            """
        )
        active_season = cur.fetchone()

        cur.execute(
            """
            SELECT l.log_id, l.action, l.entity, l.record_id, l.details, l.created_at,
                   a.full_name AS admin_name
            FROM audit_logs l
            JOIN admins a ON l.admin_id = a.admin_id
            ORDER BY l.created_at DESC
            LIMIT 8;
            """
        )
        recent_logs = cur.fetchall()

    return jsonify({
        "kpis": {
            "active_farmers": active_farmers,
            "total_submissions": total_submissions,
            "pending_submissions": pending_submissions,
            "delivered_sms": delivered_sms,
            "total_sms": total_sms,
        },
        "active_season": active_season,
        "recent_activity": recent_logs,
    }), 200


# ----------------------------------------------------------------------------
# 3. Farmers Management
# ----------------------------------------------------------------------------
@admin_bp.get("/farmers")
@admin_required
def list_farmers():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT f.farmer_id, f.phone_number, f.name, f.location,
                   f.preferred_language, f.registration_source, f.is_active,
                   f.registered_at, a.full_name AS registered_by_name
            FROM farmers f
            JOIN admins a ON f.registered_by = a.admin_id
            ORDER BY f.registered_at DESC;
            """
        )
        farmers = cur.fetchall()
    return jsonify({"farmers": farmers}), 200


@admin_bp.post("/farmers")
@admin_required
def register_farmer():
    data = request.get_json(silent=True) or {}
    phone_number = (data.get("phone_number") or "").strip()
    name = (data.get("name") or "").strip()
    location = (data.get("location") or "").strip()
    preferred_language = (data.get("preferred_language") or "rw").strip().lower()

    if not phone_number or not name or not location:
        return jsonify({"error": "Phone number, name, and location are required."}), 400

    if preferred_language not in ("en", "rw"):
        return jsonify({"error": "Preferred language must be 'en' or 'rw'."}), 400

    admin_id = g.current_admin["admin_id"]

    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM farmers WHERE phone_number = %s;", (phone_number,))
        if cur.fetchone():
            return jsonify({"error": "A farmer with this phone number is already registered."}), 409

        cur.execute(
            """
            INSERT INTO farmers (
                phone_number, name, location, preferred_language,
                registration_source, registered_by
            )
            VALUES (%s, %s, %s, %s, 'admin', %s)
            RETURNING farmer_id, phone_number, name, location, preferred_language, is_active, registered_at;
            """,
            (phone_number, name, location, preferred_language, admin_id),
        )
        farmer = cur.fetchone()

        log_admin_action(
            cur=cur,
            admin_id=admin_id,
            action="CREATE",
            entity="farmers",
            record_id=farmer["farmer_id"],
            new_value=dict(farmer),
            details=f"Registered farmer {name} ({phone_number}) in {location}.",
        )

    return jsonify({"farmer": farmer}), 201


@admin_bp.put("/farmers/<int:farmer_id>")
@admin_required
def update_farmer(farmer_id: int):
    data = request.get_json(silent=True) or {}
    admin_id = g.current_admin["admin_id"]

    with get_cursor() as cur:
        cur.execute("SELECT * FROM farmers WHERE farmer_id = %s;", (farmer_id,))
        existing = cur.fetchone()
        if not existing:
            return jsonify({"error": "Farmer not found."}), 404

        name = (data.get("name") or existing["name"]).strip()
        location = (data.get("location") or existing["location"]).strip()
        preferred_language = (data.get("preferred_language") or existing["preferred_language"]).strip().lower()
        is_active = data.get("is_active", existing["is_active"])

        cur.execute(
            """
            UPDATE farmers
            SET name = %s, location = %s, preferred_language = %s, is_active = %s
            WHERE farmer_id = %s
            RETURNING farmer_id, phone_number, name, location, preferred_language, is_active, updated_at;
            """,
            (name, location, preferred_language, bool(is_active), farmer_id),
        )
        updated = cur.fetchone()

        action_type = "DEACTIVATE" if existing["is_active"] and not updated["is_active"] else "UPDATE"
        log_admin_action(
            cur=cur,
            admin_id=admin_id,
            action=action_type,
            entity="farmers",
            record_id=farmer_id,
            old_value=dict(existing),
            new_value=dict(updated),
            details=f"Updated farmer record for {updated['name']}.",
        )

    return jsonify({"farmer": updated}), 200


# ----------------------------------------------------------------------------
# 4. Market Information Management
# ----------------------------------------------------------------------------
@admin_bp.get("/markets")
@admin_required
def list_markets():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT m.*, a.full_name AS created_by_name
            FROM market_information m
            JOIN admins a ON m.created_by = a.admin_id
            ORDER BY m.created_at DESC;
            """
        )
        markets = cur.fetchall()
    return jsonify({"markets": markets}), 200


@admin_bp.post("/markets")
@admin_required
def create_market():
    data = request.get_json(silent=True) or {}
    market_name = (data.get("market_name") or "").strip()
    location = (data.get("location") or "").strip()
    price = data.get("average_price_per_kg")
    demand_level = (data.get("demand_level") or "").strip().upper()
    source = (data.get("source") or "Field Survey").strip()

    if not market_name or not location or price is None or demand_level not in ("HIGH", "MEDIUM", "LOW"):
        return jsonify({"error": "Market name, location, valid price, and demand level are required."}), 400

    admin_id = g.current_admin["admin_id"]

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO market_information (
                market_name, location, average_price_per_kg, demand_level, source, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *;
            """,
            (market_name, location, float(price), demand_level, source, admin_id),
        )
        market = cur.fetchone()

        log_admin_action(
            cur=cur,
            admin_id=admin_id,
            action="CREATE",
            entity="market_information",
            record_id=market["market_id"],
            new_value=dict(market),
            details=f"Added market price for {market_name} at {price} RWF/kg ({demand_level} demand).",
        )

    return jsonify({"market": market}), 201


@admin_bp.put("/markets/<int:market_id>")
@admin_required
def update_market(market_id: int):
    data = request.get_json(silent=True) or {}
    admin_id = g.current_admin["admin_id"]

    with get_cursor() as cur:
        cur.execute("SELECT * FROM market_information WHERE market_id = %s;", (market_id,))
        existing = cur.fetchone()
        if not existing:
            return jsonify({"error": "Market record not found."}), 404

        market_name = (data.get("market_name") or existing["market_name"]).strip()
        location = (data.get("location") or existing["location"]).strip()
        price = data.get("average_price_per_kg", existing["average_price_per_kg"])
        demand_level = (data.get("demand_level") or existing["demand_level"]).strip().upper()
        source = (data.get("source") or existing["source"]).strip()
        is_active = data.get("is_active", existing["is_active"])

        cur.execute(
            """
            UPDATE market_information
            SET market_name = %s, location = %s, average_price_per_kg = %s,
                demand_level = %s, source = %s, is_active = %s
            WHERE market_id = %s
            RETURNING *;
            """,
            (market_name, location, float(price), demand_level, source, bool(is_active), market_id),
        )
        updated = cur.fetchone()

        log_admin_action(
            cur=cur,
            admin_id=admin_id,
            action="UPDATE",
            entity="market_information",
            record_id=market_id,
            old_value=dict(existing),
            new_value=dict(updated),
            details=f"Updated {market_name} market record ({price} RWF/kg, {demand_level} demand).",
        )

    return jsonify({"market": updated}), 200


# ----------------------------------------------------------------------------
# 5. Seasonal Information Management
# ----------------------------------------------------------------------------
@admin_bp.get("/seasons")
@admin_required
def list_seasons():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.*, a.full_name AS created_by_name
            FROM seasonal_information s
            JOIN admins a ON s.created_by = a.admin_id
            ORDER BY s.start_date DESC;
            """
        )
        seasons = cur.fetchall()
    return jsonify({"seasons": seasons}), 200


@admin_bp.post("/seasons")
@admin_required
def create_season():
    data = request.get_json(silent=True) or {}
    season_name = (data.get("season_name") or "").strip()
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    description = (data.get("description") or "").strip()
    is_active = bool(data.get("is_active", True))

    if not season_name or not start_date or not end_date or not description:
        return jsonify({"error": "Season name, start date, end date, and description are required."}), 400

    admin_id = g.current_admin["admin_id"]

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO seasonal_information (
                season_name, start_date, end_date, description, is_active, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *;
            """,
            (season_name, start_date, end_date, description, is_active, admin_id),
        )
        season = cur.fetchone()

        log_admin_action(
            cur=cur,
            admin_id=admin_id,
            action="CREATE",
            entity="seasonal_information",
            record_id=season["season_id"],
            new_value=dict(season),
            details=f"Created season '{season_name}' ({start_date} to {end_date}).",
        )

    return jsonify({"season": season}), 201


@admin_bp.put("/seasons/<int:season_id>")
@admin_required
def update_season(season_id: int):
    data = request.get_json(silent=True) or {}
    admin_id = g.current_admin["admin_id"]

    with get_cursor() as cur:
        cur.execute("SELECT * FROM seasonal_information WHERE season_id = %s;", (season_id,))
        existing = cur.fetchone()
        if not existing:
            return jsonify({"error": "Season not found."}), 404

        season_name = (data.get("season_name") or existing["season_name"]).strip()
        start_date = data.get("start_date", existing["start_date"])
        end_date = data.get("end_date", existing["end_date"])
        description = (data.get("description") or existing["description"]).strip()
        is_active = bool(data.get("is_active", existing["is_active"]))

        cur.execute(
            """
            UPDATE seasonal_information
            SET season_name = %s, start_date = %s, end_date = %s,
                description = %s, is_active = %s
            WHERE season_id = %s
            RETURNING *;
            """,
            (season_name, start_date, end_date, description, is_active, season_id),
        )
        updated = cur.fetchone()

        log_admin_action(
            cur=cur,
            admin_id=admin_id,
            action="UPDATE",
            entity="seasonal_information",
            record_id=season_id,
            old_value=dict(existing),
            new_value=dict(updated),
            details=f"Updated season '{season_name}'.",
        )

    return jsonify({"season": updated}), 200


# ----------------------------------------------------------------------------
# 6. Decision Rules Management
# ----------------------------------------------------------------------------
@admin_bp.get("/rules")
@admin_required
def list_rules():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM decision_rules ORDER BY priority ASC, rule_id ASC;")
        rules = cur.fetchall()
    return jsonify({"rules": rules}), 200


@admin_bp.post("/rules")
@admin_required
def create_rule():
    data = request.get_json(silent=True) or {}
    rule_name = (data.get("rule_name") or "").strip()
    maturity = (data.get("maturity") or "").strip().upper()
    price_trend = (data.get("price_trend") or "").strip().upper()
    demand_level = (data.get("demand_level") or "").strip().upper()
    preservation_required = bool(data.get("preservation_required", False))
    action = (data.get("action") or "").strip().upper()
    waiting_period_days = data.get("waiting_period_days")
    min_quantity_kg = data.get("min_quantity_kg")
    priority = int(data.get("priority", 1))

    if not rule_name or maturity not in ("GREEN", "TURNING", "RIPE") or action not in ("SELL_NOW", "STORE_AND_WAIT", "SEEK_ALTERNATIVE_MARKET"):
        return jsonify({"error": "Rule name, valid maturity, and valid action are required."}), 400

    # Safety rule: Never allow STORE_AND_WAIT if preservation is not required
    if action == "STORE_AND_WAIT" and not preservation_required:
        return jsonify({"error": "STORE_AND_WAIT rules must require suitable preservation."}), 400

    admin_id = g.current_admin["admin_id"]

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO decision_rules (
                rule_name, maturity, price_trend, demand_level, preservation_required,
                action, waiting_period_days, min_quantity_kg, priority
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *;
            """,
            (
                rule_name, maturity, price_trend, demand_level, preservation_required,
                action, waiting_period_days, min_quantity_kg, priority,
            ),
        )
        rule = cur.fetchone()

        log_admin_action(
            cur=cur,
            admin_id=admin_id,
            action="CREATE",
            entity="decision_rules",
            record_id=rule["rule_id"],
            new_value=dict(rule),
            details=f"Created decision rule '{rule_name}' ({action}).",
        )

    return jsonify({"rule": rule}), 201


@admin_bp.put("/rules/<int:rule_id>")
@admin_required
def update_rule(rule_id: int):
    data = request.get_json(silent=True) or {}
    admin_id = g.current_admin["admin_id"]

    with get_cursor() as cur:
        cur.execute("SELECT * FROM decision_rules WHERE rule_id = %s;", (rule_id,))
        existing = cur.fetchone()
        if not existing:
            return jsonify({"error": "Decision rule not found."}), 404

        rule_name = (data.get("rule_name") or existing["rule_name"]).strip()
        maturity = (data.get("maturity") or existing["maturity"]).strip().upper()
        price_trend = (data.get("price_trend") or existing["price_trend"]).strip().upper()
        demand_level = (data.get("demand_level") or existing["demand_level"]).strip().upper()
        preservation_required = bool(data.get("preservation_required", existing["preservation_required"]))
        action = (data.get("action") or existing["action"]).strip().upper()
        waiting_period_days = data.get("waiting_period_days", existing["waiting_period_days"])
        min_quantity_kg = data.get("min_quantity_kg", existing["min_quantity_kg"])
        priority = int(data.get("priority", existing["priority"]))
        is_active = bool(data.get("is_active", existing["is_active"]))

        if action == "STORE_AND_WAIT" and not preservation_required:
            return jsonify({"error": "STORE_AND_WAIT rules must require suitable preservation."}), 400

        cur.execute(
            """
            UPDATE decision_rules
            SET rule_name = %s,
                maturity = %s,
                price_trend = %s,
                demand_level = %s,
                preservation_required = %s,
                action = %s,
                waiting_period_days = %s,
                min_quantity_kg = %s,
                priority = %s,
                is_active = %s
            WHERE rule_id = %s
            RETURNING *;
            """,
            (
                rule_name,
                maturity,
                price_trend,
                demand_level,
                preservation_required,
                action,
                waiting_period_days,
                min_quantity_kg,
                priority,
                is_active,
                rule_id,
            ),
        )
        updated = cur.fetchone()

        action_type = "DEACTIVATE" if existing["is_active"] and not updated["is_active"] else "UPDATE"
        log_admin_action(
            cur=cur,
            admin_id=admin_id,
            action=action_type,
            entity="decision_rules",
            record_id=rule_id,
            old_value=dict(existing),
            new_value=dict(updated),
            details=f"Updated decision rule '{rule_name}'.",
        )

    return jsonify({"rule": updated}), 200


# ----------------------------------------------------------------------------
# 7. Read-Only Inspection Views (Submissions, Recommendations, SMS, Audit Logs)
# ----------------------------------------------------------------------------
@admin_bp.get("/submissions")
@admin_required
def list_submissions():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT hs.*,
                   f.name AS farmer_name,
                   f.phone_number,
                   r.recommendation_id,
                   r.action AS recommended_action,
                   r.reason AS recommendation_reason,
                   r.waiting_period_days,
                   r.confidence_level
            FROM harvest_submissions hs
            JOIN farmers f ON hs.farmer_id = f.farmer_id
            LEFT JOIN recommendations r ON hs.submission_id = r.submission_id
            ORDER BY hs.created_at DESC;
            """
        )
        submissions = cur.fetchall()
    return jsonify({"submissions": submissions}), 200


@admin_bp.get("/sms-logs")
@admin_required
def list_sms_logs():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT s.*,
                   f.name AS farmer_name
            FROM sms_logs s
            LEFT JOIN recommendations r ON s.recommendation_id = r.recommendation_id
            LEFT JOIN harvest_submissions hs ON r.submission_id = hs.submission_id
            LEFT JOIN farmers f ON hs.farmer_id = f.farmer_id
            ORDER BY s.sent_at DESC;
            """
        )
        logs = cur.fetchall()
    return jsonify({"sms_logs": logs}), 200


@admin_bp.get("/audit-logs")
@admin_required
def list_audit_logs():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT l.*,
                   a.full_name AS admin_name,
                   a.username
            FROM audit_logs l
            JOIN admins a ON l.admin_id = a.admin_id
            ORDER BY l.created_at DESC
            LIMIT 100;
            """
        )
        logs = cur.fetchall()
    return jsonify({"audit_logs": logs}), 200

