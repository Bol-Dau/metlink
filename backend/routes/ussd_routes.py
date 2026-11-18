"""
METLINK USSD & Webhook Blueprint.

Routes:
  POST /api/ussd/callback       — Africa's Talking USSD webhook
  POST /api/webhooks/sms-delivery — Africa's Talking SMS delivery report

Security: optional shared-secret token check (AT_WEBHOOK_TOKEN env var).
"""

from __future__ import annotations

import hmac
import logging
import os
from decimal import Decimal

from flask import Blueprint, make_response, request

from backend.services import engine, menus, session_store, sms_service, templates
from backend.services.farmer_lookup import get_farmer_by_phone, set_language
from database.connector import get_connection

logger = logging.getLogger(__name__)

ussd_bp = Blueprint("ussd", __name__, url_prefix="/api")

# ── Shared-secret guard ──────────────────────────────────────────────────────

def _clean_token_str(val: Optional[str]) -> str:
    if not val:
        return ""
    v = val.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()
    return v


def _check_token() -> bool:
    """
    Return True if the request is allowed.
    If AT_WEBHOOK_TOKEN is set, the query-string `token` must match it.
    If empty/unset, all requests are allowed (development only).
    """
    expected = _clean_token_str(os.getenv("AT_WEBHOOK_TOKEN"))
    if not expected:
        return True
    provided = request.args.get("token", "")
    return hmac.compare_digest(expected, provided)


def _plain(text: str, status: int = 200):
    resp = make_response(text, status)
    resp.content_type = "text/plain; charset=utf-8"
    return resp


# ── USSD Callback ────────────────────────────────────────────────────────────

@ussd_bp.post("/ussd/callback")
def ussd_callback():
    if not _check_token():
        return _plain("Forbidden", 403)

    session_id = request.form.get("sessionId", "")
    phone_raw  = request.form.get("phoneNumber", "")
    text       = request.form.get("text", "")

    masked = sms_service.mask_phone(phone_raw)
    logger.info("USSD callback sid=%s phone=%s text=%r", session_id, masked, text)

    try:
        response_text = _handle_ussd(session_id, phone_raw, text)
    except Exception:
        logger.exception("Unhandled error in USSD callback sid=%s phone=%s", session_id, masked)
        response_text = "END " + menus.screen_service_error()

    return _plain(response_text)


def _handle_ussd(session_id: str, phone_raw: str, text: str) -> str:
    """
    Core USSD handler. Returns a string starting with "CON " or "END ".
    """
    tokens = text.split("*") if text else []

    # ── 1. Farmer lookup (one connection, released immediately) ───────────────
    with get_connection() as conn:
        with conn.cursor() as cur:
            status, farmer = get_farmer_by_phone(cur, phone_raw)

    if status == "NOT_FOUND":
        return "END " + menus.screen_not_registered()
    if status == "INACTIVE":
        return "END " + menus.screen_inactive()

    # ── 2. Run stateless menu logic ───────────────────────────────────────────
    kind, payload = menus.handle(tokens, farmer)

    # ── 3. Language update (persist only when language token just selected) ───
    if tokens and tokens[0] in ("1", "2"):
        new_lang = "en" if tokens[0] == "1" else "rw"
        if new_lang != farmer.get("preferred_language"):
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        set_language(cur, farmer["farmer_id"], new_lang)
                farmer["preferred_language"] = new_lang
            except Exception:
                logger.warning("Failed to persist language for farmer %s", farmer["farmer_id"])

    # ── 4. Submissions leaf ────────────────────────────────────────────────────
    if kind == "NEED_SUBMISSIONS":
        lang = payload  # payload is the lang string here
        with get_connection() as conn:
            with conn.cursor() as cur:
                rows = engine.list_submissions(cur, farmer["farmer_id"], limit=3)
        body = menus.screen_submissions(lang, rows)
        return "END " + body

    # ── 5. Advice leaf ────────────────────────────────────────────────────────
    if kind == "NEED_ADVICE":
        lang = payload
        with get_connection() as conn:
            with conn.cursor() as cur:
                rows = engine.list_recommendations(cur, farmer["farmer_id"], limit=3)
        body = menus.screen_advice(lang, rows)
        return "END " + body

    # ── 6. Submit flow: CON or END with no DB work ────────────────────────────
    if kind in ("CON", "END"):
        return f"{kind} {payload}"

    # ── 7. DO_SUBMIT: confirm step hit ────────────────────────────────────────
    if kind != "DO_SUBMIT":
        return "END " + menus.screen_service_error()

    lang, harvest_date, quantity_kg, maturity, has_storage = payload

    # Serialise concurrent submits for the same session
    session_lock = session_store.get_session_lock(session_id)
    with session_lock:
        # Fast replay: same session already finished
        cached = session_store.get_cached_end_response(session_id)
        if cached:
            logger.info("Replay from cache sid=%s", session_id)
            return cached

        result = _do_submit(farmer, harvest_date, quantity_kg, maturity, has_storage, lang)
        session_store.cache_end_response(session_id, result)
        return result


def _do_submit(
    farmer,
    harvest_date,
    quantity_kg: Decimal,
    maturity: str,
    has_storage: bool,
    lang: str,
) -> str:
    """
    Run one transaction: duplicate check → process_harvest → commit.
    Then fire async SMS. Return the final END string.
    """
    masked = sms_service.mask_phone(farmer["phone_number"])

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Idempotency guard (cross-process)
                dup = engine.find_recent_duplicate(
                    cur,
                    farmer["farmer_id"],
                    harvest_date,
                    quantity_kg,
                    maturity,
                    has_storage,
                )
                if dup:
                    logger.info(
                        "Duplicate detected for farmer %s — returning existing result",
                        farmer["farmer_id"],
                    )
                    result = dup
                else:
                    result = engine.process_harvest(
                        cur,
                        farmer,
                        harvest_date,
                        quantity_kg,
                        maturity,
                        has_storage,
                    )
            # get_connection auto-commits on context exit

        # Dispatch SMS asynchronously (after commit, before returning to AT)
        sms_text = templates.build_sms(
            lang=lang,
            action=result["action"],
            waiting_period_days=result.get("waiting_period_days"),
            market_name=result.get("best_market_name"),
            price=result.get("best_market_price"),
        )
        sms_service.dispatch_async(result["recommendation_id"], farmer["phone_number"], sms_text)
        logger.info(
            "Submitted harvest for %s: action=%s confidence=%s",
            masked, result["action"], result["confidence_level"],
        )

        body = menus.screen_result(
            lang,
            result["action"],
            result.get("waiting_period_days"),
            result.get("best_market_name"),
            result.get("best_market_price"),
        )
        return "END " + body

    except engine.ValidationError as exc:
        logger.warning("ValidationError for %s code=%s: %s", masked, exc.code, exc)
        if exc.code == "BAD_DATE":
            msg = menus.screen_bad_date(lang, str(exc))
            return "CON " + msg
        if exc.code == "BAD_QUANTITY":
            msg = menus.screen_bad_quantity(lang, str(exc))
            return "CON " + msg
        return "END " + menus.screen_service_error()

    except Exception:
        logger.exception("Error during process_harvest for %s", masked)
        return "END " + menus.screen_service_error()


# ── SMS Delivery Webhook ─────────────────────────────────────────────────────

@ussd_bp.post("/webhooks/sms-delivery")
def sms_delivery_webhook():
    if not _check_token():
        return _plain("Forbidden", 403)

    json_data = request.get_json(silent=True) or {}
    form_data = request.form or {}

    provider_id = (
        json_data.get("id")
        or json_data.get("messageId")
        or form_data.get("id")
        or form_data.get("messageId")
        or ""
    )
    status = json_data.get("status") or form_data.get("status") or ""
    failure_reason = json_data.get("failureReason") or form_data.get("failureReason") or None

    masked_id = f"...{provider_id[-6:]}" if len(provider_id) >= 6 else (provider_id or "NONE")
    logger.info("Delivery report id=%s status=%s", masked_id, status)

    try:
        sms_service.apply_delivery_report(provider_id, status, failure_reason)
    except Exception:
        logger.exception("Error applying delivery report id=%s", masked_id)

    return _plain("OK", 200)
