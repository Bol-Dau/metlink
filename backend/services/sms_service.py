"""
METLINK Africa's Talking SMS Gateway Service.

Handles synchronous and asynchronous SMS delivery via Africa's Talking SDK,
local log_only mode, and carrier delivery receipt callbacks.
"""

from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import africastalking
from database.connector import _load_dotenv_if_present, get_cursor

logger = logging.getLogger(__name__)

# Module-level thread pool for asynchronous message delivery
_sms_executor = ThreadPoolExecutor(max_workers=4)

# Cached SDK instance
_at_sms = None
_at_initialized_creds = None


def mask_phone(phone: Optional[str]) -> str:
    """
    Masks a phone number for privacy in logs (e.g., +25078***1234).
    """
    if not phone:
        return "UNKNOWN"
    clean = str(phone).strip()
    if len(clean) >= 10:
        return f"{clean[:6]}***{clean[-4:]}"
    return f"{clean[:3]}***"


def _clean_env_val(raw: Optional[str]) -> str:
    """
    Strips whitespace and optional enclosing single/double quotes.
    """
    if raw is None:
        return ""
    val = raw.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1].strip()
    return val


def get_sms_config() -> Dict[str, Any]:
    """
    Loads SMS configuration lazily from environment variables after ensuring
    .env is loaded. Strips whitespace and surrounding quotes from every value.
    """
    _load_dotenv_if_present()

    raw_username = _clean_env_val(os.getenv("AT_USERNAME"))
    raw_api_key = _clean_env_val(os.getenv("AT_API_KEY"))
    raw_sender_id = _clean_env_val(os.getenv("AT_SENDER_ID"))
    raw_mode = _clean_env_val(os.getenv("SMS_MODE")).lower()

    # In Africa's Talking, sandbox username must be strictly "sandbox"
    if not raw_username or raw_username.lower() == "sandbox":
        username = "sandbox"
    else:
        username = raw_username

    # Resolve mode: case-insensitive; only "live" or "log_only" are valid
    if not raw_mode:
        mode = "live" if raw_api_key else "log_only"
    elif raw_mode in ("live", "log_only"):
        mode = raw_mode
    else:
        mode = "log_only"

    # Sender ID: None if empty/whitespace (never empty string)
    sender_id = raw_sender_id if raw_sender_id else None

    return {
        "username": username,
        "api_key": raw_api_key,
        "sender_id": sender_id,
        "mode": mode,
    }


def _get_at_sms_client(username: str, api_key: str):
    """
    Initializes and returns the Africa's Talking SMS client singleton lazily.
    """
    global _at_sms, _at_initialized_creds
    creds = (username, api_key)
    if _at_sms is None or _at_initialized_creds != creds:
        africastalking.initialize(username, api_key)
        _at_sms = africastalking.SMS
        _at_initialized_creds = creds
    return _at_sms


def default_sms_provider(phone_number: str, message: str) -> Dict[str, Any]:
    """
    Default Africa's Talking SMS provider using the official SDK.
    Never logs the API key.
    """
    config = get_sms_config()
    username = config["username"]
    api_key = config["api_key"]
    sender_id = config["sender_id"]

    sms_client = _get_at_sms_client(username, api_key)

    # Attempt send (with sender_id if configured)
    response = None
    try:
        response = sms_client.send(
            message=message,
            recipients=[phone_number],
            sender_id=sender_id,
        )
    except Exception as exc:
        if sender_id and username == "sandbox":
            logger.warning(
                "Sandbox rejected sender_id '%s' (%s). Retrying without sender_id.",
                sender_id,
                exc,
            )
            response = sms_client.send(
                message=message,
                recipients=[phone_number],
                sender_id=None,
            )
        else:
            raise

    # In sandbox, Africa's Talking may return InvalidSenderId inside the response
    if isinstance(response, dict):
        sms_data = response.get("SMSMessageData", {})
        msg_header = str(sms_data.get("Message", ""))
        recipients = sms_data.get("Recipients", [])
        if sender_id and username == "sandbox":
            has_invalid_sender = (
                "invalidsenderid" in msg_header.lower()
                or any(r.get("status") == "InvalidSenderId" for r in recipients)
                or (not recipients and "invalid" in msg_header.lower())
            )
            if has_invalid_sender:
                logger.warning(
                    "Sandbox returned '%s' with sender_id '%s'. Retrying without sender_id.",
                    msg_header or "InvalidSenderId",
                    sender_id,
                )
                response = sms_client.send(
                    message=message,
                    recipients=[phone_number],
                    sender_id=None,
                )

    if not isinstance(response, dict) or "SMSMessageData" not in response:
        logger.error(
            "Unexpected Africa's Talking response structure: %s",
            {k: type(v).__name__ for k, v in response.items()} if isinstance(response, dict) else type(response).__name__,
        )
        raise RuntimeError("Invalid response structure from Africa's Talking.")

    recipients = response.get("SMSMessageData", {}).get("Recipients", [])
    if not recipients:
        msg_header = response.get("SMSMessageData", {}).get("Message", "Empty recipients list")
        logger.error("Africa's Talking returned empty recipients. Message header: %s", msg_header)
        raise RuntimeError(f"Africa's Talking returned no recipients: {msg_header}")

    recipient = recipients[0]
    status_text = str(recipient.get("status", "")).strip()
    status_code = recipient.get("statusCode")
    message_id = recipient.get("messageId")

    is_success = (status_text.lower() == "success") or (status_code in (100, 101, 102))
    if not is_success or not message_id:
        logger.error(
            "Africa's Talking delivery rejected: status='%s' statusCode=%s messageId=%s",
            status_text,
            status_code,
            message_id,
        )
        raise RuntimeError(
            f"Africa's Talking rejected send: status='{status_text}', statusCode={status_code}"
        )

    return {
        "provider_id": message_id,
        "status": status_text,
        "status_code": status_code,
        "raw_response": response,
    }


# Replaceable provider function for test mocking
_provider_fn: Callable[[str, str], Dict[str, Any]] = default_sms_provider


def set_sms_provider(provider_fn: Callable[[str, str], Dict[str, Any]]) -> None:
    """Sets a custom provider function for testing."""
    global _provider_fn
    _provider_fn = provider_fn


def reset_sms_provider() -> None:
    """Restores the default Africa's Talking SDK provider."""
    global _provider_fn
    _provider_fn = default_sms_provider


def _insert_sms_log_with_retry(
    recommendation_id: int,
    phone_number: str,
    message: str,
    status: str,
    provider_id: Optional[str] = None,
    delivered_at: Optional[Any] = None,
) -> Optional[int]:
    """
    Guarantees an sms_logs row is inserted.
    If the first insert attempt fails, logs ERROR with logger.exception
    and retries once on a fresh cursor.
    """
    for attempt in range(2):
        try:
            with get_cursor() as cur:
                if delivered_at is not None:
                    cur.execute(
                        """
                        INSERT INTO sms_logs (
                            recommendation_id, phone_number, message, status, provider_id, sent_at, delivered_at
                        )
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
                        RETURNING sms_id;
                        """,
                        (recommendation_id, phone_number, message, status, provider_id, delivered_at),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO sms_logs (
                            recommendation_id, phone_number, message, status, provider_id, sent_at
                        )
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        RETURNING sms_id;
                        """,
                        (recommendation_id, phone_number, message, status, provider_id),
                    )
                row = cur.fetchone()
                return row["sms_id"] if row else None
        except Exception:
            logger.exception(
                "Attempt %d: Failed to insert sms_logs row (phone=%s, status=%s)",
                attempt + 1,
                mask_phone(phone_number),
                status,
            )
            if attempt == 1:
                return None
    return None


def send_sms_sync(
    recommendation_id: int,
    phone_number: str,
    message: str,
) -> Dict[str, Any]:
    """
    Sends an SMS message synchronously and logs the outcome to sms_logs.

    Guarantees that every path creates exactly one sms_logs row.
    Uses its own database cursor to commit independently.
    NEVER raises an exception to the caller: provider errors become a FAILED row.
    """
    masked = mask_phone(phone_number)
    final_status = "FAILED"
    final_provider_id = None
    final_delivered_at = None

    try:
        config = get_sms_config()
        mode = config["mode"]
        logger.info("SMS send dispatch mode=%s to %s (rec_id=%s)", mode, masked, recommendation_id)

        # 1. log_only mode
        if mode == "log_only":
            logger.warning(
                "SMS in log_only mode: simulated send to %s (no SMS transmitted to carrier)",
                masked,
            )
            final_status = "SENT"
            final_provider_id = None
            return {"status": "SENT", "provider_id": None}

        # 2. live mode: verify required credentials
        missing_keys = []
        if not config["username"]:
            missing_keys.append("AT_USERNAME")
        if not config["api_key"]:
            missing_keys.append("AT_API_KEY")

        if missing_keys:
            logger.error(
                "SMS live mode cannot send: missing required key(s): %s",
                ", ".join(missing_keys),
            )
            final_status = "FAILED"
            final_provider_id = None
            return {"status": "FAILED", "provider_id": None}

        # 3. live mode via provider
        res = _provider_fn(phone_number, message)
        provider_id = None
        is_success = False
        status_text = ""
        status_code = None

        if isinstance(res, dict):
            if "SMSMessageData" in res:
                recipients = res.get("SMSMessageData", {}).get("Recipients", [])
                if recipients:
                    r0 = recipients[0]
                    provider_id = r0.get("messageId")
                    status_text = str(r0.get("status", "")).strip()
                    status_code = r0.get("statusCode")
                    is_success = (status_text.lower() == "success") or (status_code in (100, 101, 102))
                    if not is_success:
                        logger.error(
                            "Africa's Talking recipient error: status='%s' statusCode=%s",
                            status_text,
                            status_code,
                        )
                else:
                    msg_header = res.get("SMSMessageData", {}).get("Message", "Empty recipients list")
                    logger.error("Africa's Talking returned no recipients: %s", msg_header)
            else:
                provider_id = res.get("provider_id")
                status_text = str(res.get("status", "")).strip()
                status_code = res.get("status_code")
                is_success = (
                    (status_text.lower() in ("success", "sent"))
                    or (status_code in (100, 101, 102))
                )
                if not is_success:
                    logger.error(
                        "Provider returned non-success: status='%s' statusCode=%s",
                        status_text,
                        status_code,
                    )

        if is_success and provider_id:
            final_status = "SENT"
            final_provider_id = provider_id

            # Sandbox auto-delivered convenience check
            raw_auto = _clean_env_val(os.getenv("SMS_SANDBOX_AUTO_DELIVERED")).lower()
            if raw_auto == "true" and config.get("username") == "sandbox":
                final_status = "DELIVERED"
                final_delivered_at = datetime.now()
                logger.warning("sandbox auto-delivered, no delivery report received")
        else:
            final_status = "FAILED"
            final_provider_id = None

    except Exception:
        logger.exception("Failed to send live SMS to %s", masked)
        final_status = "FAILED"
        final_provider_id = None
        final_delivered_at = None

    finally:
        _insert_sms_log_with_retry(
            recommendation_id=recommendation_id,
            phone_number=phone_number,
            message=message,
            status=final_status,
            provider_id=final_provider_id,
            delivered_at=final_delivered_at,
        )

    return {"status": final_status, "provider_id": final_provider_id}


def _async_sms_worker(recommendation_id: int, phone_number: str, message: str) -> Dict[str, Any]:
    try:
        return send_sms_sync(recommendation_id, phone_number, message)
    except Exception:
        logger.exception(
            "Unhandled exception in SMS async thread for %s",
            mask_phone(phone_number),
        )
        raise


def _on_future_done(future):
    try:
        exc = future.exception()
        if exc:
            logger.error("SMS background execution failed with exception: %s", exc)
    except Exception:
        logger.exception("Error checking SMS future completion status")


def dispatch_async(
    recommendation_id: int,
    phone_number: str,
    message: str,
) -> None:
    """
    Submits SMS delivery to the background thread pool and returns immediately.
    Logs any background exception through both wrapper and future callback.
    """
    future = _sms_executor.submit(_async_sms_worker, recommendation_id, phone_number, message)
    future.add_done_callback(_on_future_done)


def apply_delivery_report(
    provider_id: str,
    status: str,
    failure_reason: Optional[str] = None,
) -> bool:
    """
    Applies Africa's Talking delivery report callback.

    Race guard: if no row matches in sms_logs, retries up to 3 times
    with a 300 ms pause before giving up.
    CRITICAL: Never downgrades an already 'DELIVERED' row.
    Returns True if a row's status was updated, False otherwise.
    """
    if not provider_id:
        return False

    raw_status = (status or "").strip().lower()
    if raw_status == "success":
        target_status = "DELIVERED"
    elif raw_status in ("failed", "rejected"):
        target_status = "FAILED"
    else:
        # Transient intermediate statuses (Sent, Submitted, Buffered, etc.)
        return False

    for attempt in range(4):
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT sms_id, status
                FROM sms_logs
                WHERE provider_id = %s;
                """,
                (provider_id,),
            )
            row = cur.fetchone()
            if row:
                current_status = row["status"]
                if current_status == "DELIVERED":
                    # Never downgrade a delivered message
                    return False

                if target_status == "DELIVERED":
                    cur.execute(
                        """
                        UPDATE sms_logs
                        SET status = 'DELIVERED',
                            delivered_at = CURRENT_TIMESTAMP
                        WHERE provider_id = %s;
                        """,
                        (provider_id,),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE sms_logs
                        SET status = 'FAILED'
                        WHERE provider_id = %s;
                        """,
                        (provider_id,),
                    )
                return cur.rowcount > 0

        if attempt < 3:
            time.sleep(0.3)

    logger.info("Delivery report received for unknown provider_id: %s (after 3 retries)", provider_id)
    return False
