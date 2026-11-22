"""
Farmer phone normalization and lookup service for METLINK USSD/SMS.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

VALID_RWANDA_PREFIXES = ("72", "73", "78", "79")


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """
    Normalizes a Rwandan phone number to E.164 format (+250XXXXXXXXX).

    Accepts formats such as:
    - 0788123456
    - 788123456
    - 250788123456
    - +250788123456
    with optional spaces, dashes, or parentheses.

    Returns the normalized string, or None if the phone number is invalid.
    A valid Rwandan mobile number has exactly 9 digits following +250
    and starts with 72, 73, 78, or 79.
    """
    if raw is None:
        return None

    cleaned = re.sub(r"[\s\-\(\)]", "", str(raw).strip())
    if not cleaned:
        return None

    digits = cleaned[1:] if cleaned.startswith("+") else cleaned
    if not digits.isdigit():
        return None

    if digits.startswith("250"):
        local = digits[3:]
    elif digits.startswith("0"):
        local = digits[1:]
    else:
        local = digits

    if len(local) != 9:
        return None

    if not local.startswith(VALID_RWANDA_PREFIXES):
        return None

    return f"+250{local}"


def get_farmer_by_phone(cur: Any, raw: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Look up a farmer by phone number.

    Returns:
        (status, farmer)
        where status is 'ACTIVE', 'INACTIVE', or 'NOT_FOUND'.
        farmer is a dictionary of farmer columns or None.

    Farmers are registered only by admins; this function never creates farmers.
    """
    phone = normalize_phone(raw)
    if phone is None:
        return "NOT_FOUND", None

    cur.execute(
        """
        SELECT farmer_id, phone_number, name, location, preferred_language,
               registration_source, registered_by, is_active, registered_at, updated_at
        FROM farmers
        WHERE phone_number = %s;
        """,
        (phone,),
    )
    row = cur.fetchone()

    if not row:
        return "NOT_FOUND", None

    farmer = dict(row)
    if farmer.get("is_active"):
        return "ACTIVE", farmer
    return "INACTIVE", farmer


def set_language(cur: Any, farmer_id: int, lang: str) -> bool:
    """
    Update a farmer's preferred language ('en' or 'rw').

    Returns True if updated successfully, False if farmer not found.
    Raises ValueError on unsupported language.
    """
    if lang not in ("en", "rw"):
        raise ValueError(f"Invalid language '{lang}': must be 'en' or 'rw'")

    cur.execute(
        """
        UPDATE farmers
        SET preferred_language = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE farmer_id = %s;
        """,
        (lang, farmer_id),
    )
    return cur.rowcount > 0
