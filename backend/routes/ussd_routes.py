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
import time
from decimal import Decimal
from typing import Optional

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


def make_ussd_response(body: str):
    """
    Guarantees:
    - body starts with 'CON ' or 'END ' (otherwise forces error END)
    - no leading whitespace
    - at most 182 characters (truncates dynamic text with warning)
    - Content-Type exactly 'text/plain; charset=utf-8'
    - status 200
    """
    clean = (body or "").lstrip()
    if not (clean.startswith("CON ") or clean.startswith("END ")):
        clean = "END " + menus.screen_service_error()

    if len(clean) > 182:
        logger.warning(
            "Truncating USSD response exceeding 182 chars (%d chars): %r",
            len(clean),
            clean,
        )
        clean = clean[:181] + "~"

    resp = make_response(clean, 200)
    resp.content_type = "text/plain; charset=utf-8"
    return resp


@ussd_bp.app_errorhandler(404)
def _handle_ussd_404(err):
    if request.path.startswith("/api/ussd"):
        return make_ussd_response("END " + menus.screen_service_error())
    return err


@ussd_bp.app_errorhandler(405)
def _handle_ussd_405(err):
    if request.path.startswith("/api/ussd"):
        return make_ussd_response("END " + menus.screen_service_error())
    return err


# ── USSD Callback ────────────────────────────────────────────────────────────

@ussd_bp.post("/ussd/callback")
def ussd_callback():
    start_time = time.monotonic()
    session_id = request.form.get("sessionId", "")
    phone_raw  = request.form.get("phoneNumber", "")
    text       = request.form.get("text", "")
    masked = sms_service.mask_phone(phone_raw)

    logger.info("USSD callback sid=%s phone=%s text=%r", session_id, masked, text)

    try:
        # A wrong token returns 403 (this is a configuration error)
        if not _check_token():
            return _plain("Forbidden", 403)

        response_text = _handle_ussd(session_id, phone_raw, text)
        resp = make_ussd_response(response_text)
    except Exception:
        logger.exception("Unhandled error in USSD callback sid=%s phone=%s", session_id, masked)
        resp = make_ussd_response("END " + menus.screen_service_error())

    elapsed_ms = (time.monotonic() - start_time) * 1000.0
    step_hint = text.split("*")[-1] if text else "root"
    logger.info("USSD callback finished sid=%s step=%s elapsed=%.1fms", session_id, step_hint, elapsed_ms)
    if elapsed_ms > 1000.0:
        logger.warning("USSD callback took >1000ms: sid=%s elapsed=%.1fms", session_id, elapsed_ms)

    return resp


def _handle_ussd(session_id: str, phone_raw: str, text: str) -> str:
    """
    Core USSD handler. Returns a string starting with "CON " or "END ".
    """
    acquired = session_store.acquire_session_lock(session_id, timeout=5.0)
    if not acquired:
        logger.warning("Session lock acquisition timed out for sid=%s", session_id)
        return "END " + menus.screen_service_error()

    try:
        cached = session_store.get_cached_response(session_id, text)
        if cached:
            logger.info("Replay from cache sid=%s text=%r", session_id, text)
            return cached

        tokens = text.split("*") if text else []

        # ── 1. Farmer lookup (one connection, released immediately) ───────────────
        with get_connection() as conn:
            with conn.cursor() as cur:
                status, farmer = get_farmer_by_phone(cur, phone_raw)

        if status == "NOT_FOUND":
            res = "END " + menus.screen_not_registered()
            session_store.cache_response(session_id, text, res)
            return res
        if status == "INACTIVE":
            res = "END " + menus.screen_inactive()
            session_store.cache_response(session_id, text, res)
            return res

        # ── 2. Run stateless menu logic ───────────────────────────────────────────
        kind, payload = menus.handle(tokens, farmer)

        # ── 3. Language update (persist when valid language choice made) ──────────
        chosen_lang = None
        for t in tokens:
            tok = t.strip()
            if tok in ("1", "2"):
                chosen_lang = "en" if tok == "1" else "rw"
                break
        if chosen_lang and chosen_lang != farmer.get("preferred_language"):
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        set_language(cur, farmer["farmer_id"], chosen_lang)
                farmer["preferred_language"] = chosen_lang
            except Exception:
                logger.warning("Failed to persist language for farmer %s", farmer["farmer_id"])

        # ── 4. Submissions leaf ────────────────────────────────────────────────────
        if kind == "NEED_SUBMISSIONS":
            lang = payload
            with get_connection() as conn:
                with conn.cursor() as cur:
                    rows = engine.list_submissions(cur, farmer["farmer_id"], limit=3)
            body = menus.screen_submissions(lang, rows)
            res = "END " + body
            session_store.cache_response(session_id, text, res)
            return res

        # ── 5. Advice leaf ────────────────────────────────────────────────────────
        if kind == "NEED_ADVICE":
            lang = payload
            with get_connection() as conn:
                with conn.cursor() as cur:
                    rows = engine.list_recommendations(cur, farmer["farmer_id"], limit=3)
            body = menus.screen_advice(lang, rows)
            res = "END " + body
            session_store.cache_response(session_id, text, res)
            return res

        # ── 6. Submit flow: CON or END with no DB work ────────────────────────────
        if kind in ("CON", "END"):
            res = f"{kind} {payload}"
            session_store.cache_response(session_id, text, res)
            return res

        # ── 7. DO_SUBMIT: confirm step hit ────────────────────────────────────────
        if kind != "DO_SUBMIT":
            res = "END " + menus.screen_service_error()
            session_store.cache_response(session_id, text, res)
            return res

        lang, harvest_date, quantity_kg, maturity, has_storage = payload

        result = _do_submit(farmer, harvest_date, quantity_kg, maturity, has_storage, lang)
        session_store.cache_response(session_id, text, result)
        return result

    finally:
        session_store.release_session_lock(session_id)


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
            msg = menus.screen_ask_date(lang, error=str(exc))
            return "CON " + msg
        if exc.code == "BAD_QUANTITY":
            msg = menus.screen_ask_quantity(lang, harvest_date, error=str(exc))
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
