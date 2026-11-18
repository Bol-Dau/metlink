# REVIEW: Kinyarwanda needs a native speaker review before demo.
"""
Bilingual SMS templates for METLINK harvest recommendations.

Generates GSM-7 safe text within 160 characters for Rwanda telco SMS delivery.
"""

from __future__ import annotations

import re
from typing import Any, Optional

GSM7_REPLACEMENTS = {
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "—": "-",
    "–": "-",
    "…": "...",
    "é": "e",
    "è": "e",
    "ê": "e",
    "à": "a",
    "â": "a",
    "î": "i",
    "ï": "i",
    "ô": "o",
    "ù": "u",
    "û": "u",
}

DISCLAIMER_EN = "Guide only, not a guarantee."
DISCLAIMER_RW = "Inama gusa, nta kwishingira."


def sanitize_gsm7(text: str) -> str:
    """
    Replaces unicode punctuation and accented characters with GSM-7 safe ASCII equivalents.
    """
    for char, replacement in GSM7_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Remove any non-ASCII characters that remain
    return re.sub(r"[^\x20-\x7E]", "", text)


def format_action_text(lang: str, action: str, waiting_period_days: Optional[int]) -> str:
    """
    Returns the action phrase in the chosen language.
    """
    is_rw = lang.lower() == "rw"

    if action == "SELL_NOW":
        return "METLINK: Gurisha ubu." if is_rw else "METLINK: Sell now."

    if action == "STORE_AND_WAIT":
        days = waiting_period_days if waiting_period_days is not None else 0
        if is_rw:
            return f"METLINK: Bika utegereze iminsi {days}."
        return f"METLINK: Store and wait for {days} days."

    if action == "SEEK_ALTERNATIVE_MARKET":
        return "METLINK: Shakisha irindi soko." if is_rw else "METLINK: Seek alternative market."

    return f"METLINK: {action}."


def build_sms(
    lang: str,
    action: str,
    waiting_period_days: Optional[int] = None,
    market_name: Optional[str] = None,
    price: Optional[Any] = None,
) -> str:
    """
    Builds a single SMS message of at most 160 GSM-7 safe characters.

    Always includes:
    1. Recommendation action (with waiting days for STORE_AND_WAIT)
    2. Best market and price (if provided and fits within 160 characters)
    3. Mandatory non-guarantee guide disclaimer line (never omitted)

    If too long, shortens the market name first, then drops the market part entirely.
    The disclaimer is NEVER dropped.
    """
    is_rw = (lang or "en").lower() == "rw"
    disclaimer = DISCLAIMER_RW if is_rw else DISCLAIMER_EN
    action_text = format_action_text(lang, action, waiting_period_days)

    has_market = market_name and price is not None
    if has_market:
        try:
            formatted_price = f"{float(price):,.0f}"
        except (ValueError, TypeError):
            formatted_price = str(price)

        prefix = "Isoko: " if is_rw else "Market: "
        suffix = f" ({formatted_price} RWF/kg)."

        # Try full message first
        market_part = f"{prefix}{market_name}{suffix}"
        message = f"{action_text} {market_part} {disclaimer}"

        if len(message) > 160:
            # Shorten market name
            fixed_overhead = len(action_text) + len(disclaimer) + len(prefix) + len(suffix) + 2
            available_for_name = 160 - fixed_overhead
            if available_for_name >= 6:
                short_market = market_name[: available_for_name - 3].strip() + "..."
                market_part = f"{prefix}{short_market}{suffix}"
                message = f"{action_text} {market_part} {disclaimer}"
            else:
                # Drop market part completely
                message = f"{action_text} {disclaimer}"
    else:
        message = f"{action_text} {disclaimer}"

    sanitized = sanitize_gsm7(message)
    if len(sanitized) > 160:
        # Fallback to absolute minimum: action + disclaimer
        sanitized = sanitize_gsm7(f"{action_text} {disclaimer}")
        if len(sanitized) > 160:
            sanitized = sanitized[:160]

    return sanitized
