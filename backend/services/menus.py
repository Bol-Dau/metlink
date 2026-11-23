# REVIEW: Kinyarwanda needs a native speaker review before demo.
"""
METLINK USSD Menus and Stateless Step Machine Engine.

Pure folding function handle(tokens, farmer) -> (kind, payload)
Contract:
- Left-to-right fold across tokens through a step machine.
- Each token is stripped of whitespace.
- Valid tokens advance step and push to history stack.
- Invalid tokens do not change step or data; if last token, re-prompts screen with error prepended.
- "0" after main menu pops stack (back one step), discarding data collected at that step.
- "0" on language screen and main menu is an invalid choice (no back).
- Single-step date entry (ENTER_DATE): validates full calendar date in Africa/Kigali timezone.
- Screens fit <= 160 characters where practical, hard maximum 182.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from backend.services.engine import MAX_DAYS_AHEAD, MAX_QUANTITY_KG

logger = logging.getLogger(__name__)

KIGALI_TZ = ZoneInfo("Africa/Kigali")
USSD_MAX_CHARS = 182

# Steps
STEP_LANG = "SELECT_LANG"
STEP_MAIN = "MAIN_MENU"
STEP_DATE = "ENTER_DATE"
STEP_QTY = "ENTER_QUANTITY"
STEP_MATURITY = "SELECT_MATURITY"
STEP_STORAGE = "SELECT_STORAGE"
STEP_CONFIRM = "CONFIRM_SUBMISSION"

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_RIPENESS_MAP = {"1": "GREEN", "2": "TURNING", "3": "RIPE"}


def get_today_kigali() -> date:
    return datetime.now(KIGALI_TZ).date()


def format_readable_date(d: date) -> str:
    """Format a date as '25 Nov 2026'."""
    return f"{d.day} {MONTH_NAMES[d.month - 1]} {d.year}"


def parse_harvest_date(raw: str, today: Optional[date] = None) -> Tuple[Optional[date], Optional[str]]:
    """
    Parses and validates a raw harvest date string.
    Rules:
      - Strip whitespace.
      - If separated (- / . space): exactly 3 parts: day (1-2 digits), month (1-2 digits), year (4 digits).
      - If no separators: exactly 8 digits read as DDMMYYYY.
      - Reject anything else as BAD_FORMAT.
      - Check calendar validity (e.g. 31-02-2026, 29-02-2027) -> BAD_CALENDAR.
      - Check past date (< today) -> PAST. (today is accepted).
      - Check too far ahead (> today + MAX_DAYS_AHEAD) -> TOO_FAR.
    Returns: (parsed_date, None) or (None, error_code).
    """
    if today is None:
        today = get_today_kigali()

    token = (raw or "").strip()
    if not token:
        return None, "BAD_FORMAT"

    has_sep = any(c in token for c in "-/. ")
    if has_sep:
        parts = re.split(r"[-/.\s]+", token)
        if len(parts) != 3:
            return None, "BAD_FORMAT"
        d_str, m_str, y_str = parts
        if not (d_str.isdigit() and m_str.isdigit() and y_str.isdigit()):
            return None, "BAD_FORMAT"
        if not (1 <= len(d_str) <= 2 and 1 <= len(m_str) <= 2 and len(y_str) == 4):
            return None, "BAD_FORMAT"
        d_val, m_val, y_val = int(d_str), int(m_str), int(y_str)
    else:
        if not (token.isdigit() and len(token) == 8 and not token.startswith(("+", "-"))):
            return None, "BAD_FORMAT"
        d_val = int(token[0:2])
        m_val = int(token[2:4])
        y_val = int(token[4:8])

    # Calendar validity
    try:
        candidate = date(y_val, m_val, d_val)
    except ValueError:
        return None, "BAD_CALENDAR"

    # Past date check
    if candidate < today:
        return None, "PAST"

    # Too far ahead
    if candidate > today + timedelta(days=MAX_DAYS_AHEAD):
        return None, "TOO_FAR"

    return candidate, None


def fit(text: str, budget: int) -> str:
    """Truncate dynamic values to budget characters."""
    if len(text) <= budget:
        return text
    return text[: budget - 1] + "~"


def _t(lang: str, en: str, rw: str) -> str:
    return rw if lang == "rw" else en


# ── Screen Generators ─────────────────────────────────────────────────────────

def screen_language(error: Optional[str] = None) -> str:
    prompt = "METLINK\n1. English\n2. Kinyarwanda"
    if error:
        return f"{error}\n{prompt}"
    return prompt


def screen_main(lang: str, name: str, error: Optional[str] = None) -> str:
    short = fit(name, 16)
    prompt = _t(
        lang,
        f"Hello {short}\n1. Submit expected harvest\n2. My submissions\n3. My advice",
        f"Muraho {short}\n1. Ohereza umusaruro\n2. Ibyanjye\n3. Inama zanjye",
    )
    if error:
        return f"{error}\n{prompt}"
    return prompt


# REVIEW: Kinyarwanda needs a native speaker review before demo.
def screen_ask_date(lang: str, today: Optional[date] = None, error: Optional[str] = None) -> str:
    if today is None:
        today = get_today_kigali()
    ex_date = today + timedelta(days=30)
    example = ex_date.strftime("%d-%m-%Y")
    prompt = _t(
        lang,
        f"Enter harvest date (DD-MM-YYYY or DDMMYYYY, e.g. {example}):\n0. Back",
        f"Andika itariki yo gusarura (DD-MM-YYYY cyangwa DDMMYYYY, urugero: {example}):\n0. Subira inyuma",
    )
    if error:
        return f"{error}\n{prompt}"
    return prompt


def screen_ask_quantity(lang: str, harvest_date: Optional[date] = None, error: Optional[str] = None) -> str:
    header = f"Date: {format_readable_date(harvest_date)}\n" if harvest_date else ""
    prompt = _t(
        lang,
        f"{header}Enter Quantity in kg (whole number):\n0. Back",
        f"{header}Kwinjira Ingano muri kg (umubare wuzuye):\n0. Subira",
    )
    if error:
        return f"{error}\n{prompt}"
    return prompt


def screen_ask_maturity(lang: str, error: Optional[str] = None) -> str:
    prompt = _t(
        lang,
        "Tomato ripeness:\n1. Green\n2. Turning\n3. Ripe\n0. Back",
        "Ibara ry'inyanya:\n1. Ntimera\n2. Rinda\n3. Imeze\n0. Subira",
    )
    if error:
        return f"{error}\n{prompt}"
    return prompt


def screen_ask_storage(lang: str, error: Optional[str] = None) -> str:
    prompt = _t(
        lang,
        "Do you have a safe place to store tomatoes (cool, ventilated)?\n1. Yes\n2. No\n0. Back",
        "Ufite aho kubika inyanya hizewe (ahakonje, hahumeka)?\n1. Yego\n2. Oya\n0. Subira",
    )
    if error:
        return f"{error}\n{prompt}"
    return prompt


def screen_confirm(
    lang: str,
    harvest_date: date,
    quantity_kg: Decimal,
    maturity: str,
    has_storage: bool,
    error: Optional[str] = None,
) -> str:
    d_str = format_readable_date(harvest_date)
    mat_lbl = {
        "GREEN": _t(lang, "Green", "Ntimera"),
        "TURNING": _t(lang, "Turning", "Rinda"),
        "RIPE": _t(lang, "Ripe", "Imeze"),
    }.get(maturity, maturity)
    stor_lbl = _t(lang, "Yes" if has_storage else "No", "Yego" if has_storage else "Oya")

    prompt = _t(
        lang,
        f"Confirm harvest:\nDate: {d_str}\nQty: {int(quantity_kg)}kg\n"
        f"Maturity: {mat_lbl}\nStorage: {stor_lbl}\n"
        f"1. Confirm & Submit\n2. Cancel\n0. Back",
        f"Emeza umusaruro:\nItariki: {d_str}\nIbiro: {int(quantity_kg)}kg\n"
        f"Ibyiciro: {mat_lbl}\nUbubiko: {stor_lbl}\n"
        f"1. Emeza wohereze\n2. Hagarika\n0. Subira",
    )
    if error:
        return f"{error}\n{prompt}"
    return prompt


def screen_cancelled(lang: str) -> str:
    return _t(
        lang,
        "Cancelled Submission",
        "Ubusabe Bwahagaritswe",
    )


def screen_result(
    lang: str,
    action: str,
    waiting_period_days: Optional[int],
    best_market_name: Optional[str],
    best_market_price: Optional[Any],
) -> str:
    if action == "SELL_NOW":
        action_lbl = _t(lang, "Sell now", "Gurisha ubu")
    elif action == "STORE_AND_WAIT":
        d = waiting_period_days or 0
        action_lbl = _t(lang, f"Store {d}d", f"Bika {d}d")
    else:
        action_lbl = _t(lang, "Alt market", "Soko rindi")

    if best_market_name and best_market_price is not None:
        mkt = fit(str(best_market_name), 14)
        try:
            price_fmt = f"{float(best_market_price):,.0f}"
        except (TypeError, ValueError):
            price_fmt = str(best_market_price)
        market_part = f"\n{_t(lang, 'Market', 'Isoko')}: {mkt} {price_fmt}RWF"
    else:
        market_part = ""

    guide = _t(lang, "Details by SMS. Guide only.", "Soma SMS. Inama gusa.")
    return _t(
        lang,
        f"Advice: {action_lbl}{market_part}\n{guide}",
        f"Inama: {action_lbl}{market_part}\n{guide}",
    )


def screen_submissions(lang: str, rows: list) -> str:
    if not rows:
        return _t(lang, "No submissions yet.", "Nta raporo iriho.")
    lines = [_t(lang, "Last submissions:", "Raporo zaheruka:")]
    for r in rows:
        d = r["expected_harvest_date"]
        date_str = d.strftime("%d/%m") if hasattr(d, "strftime") else str(d)[:5]
        mat = {
            "GREEN": _t(lang, "Green", "Ntimera"),
            "TURNING": _t(lang, "Turning", "Rinda"),
            "RIPE": _t(lang, "Ripe", "Imeze"),
        }.get(r["tomato_maturity"], r["tomato_maturity"])
        qty = int(r["quantity_kg"])
        lines.append(f"{date_str} {qty}kg {mat}")
    return "\n".join(lines)


def screen_advice(lang: str, rows: list) -> str:
    if not rows:
        return _t(lang, "No advice yet.", "Nta nama iriho.")
    lines = [_t(lang, "Last advice:", "Inama zaheruka:")]
    for r in rows:
        d = r["expected_harvest_date"]
        date_str = d.strftime("%d/%m") if hasattr(d, "strftime") else str(d)[:5]
        act = r["action"]
        if act == "SELL_NOW":
            act_lbl = _t(lang, "Sell now", "Gurisha ubu")
        elif act == "STORE_AND_WAIT":
            act_lbl = _t(lang, f"Store {r.get('waiting_period_days') or 0}d", f"Bika {r.get('waiting_period_days') or 0}d")
        else:
            act_lbl = _t(lang, "Alt market", "Soko rindi")
        lines.append(f"{date_str} {act_lbl}")
    return "\n".join(lines)


def screen_service_error() -> str:
    return "Service error. Try again later. / Habaye ikibazo. Ongera ugerageze nyuma."


def screen_not_registered() -> str:
    return (
        "This number is not registered. Contact your administrator. / "
        "Iyi nimero ntiyanditswe. Vugana n'umuyobozi."
    )


def screen_inactive() -> str:
    return (
        "Account inactive. Contact your administrator. / "
        "Konti yawe irahagaritswe. Vugana n'umuyobozi."
    )


# ── Step Machine Folding ──────────────────────────────────────────────────────

def _is_strictly_digits(s: str) -> bool:
    return bool(s) and s.isdigit() and not s.startswith(("+", "-", " "))


def handle(tokens: List[str], farmer: Dict[str, Any]) -> Tuple[str, Any]:
    """
    Folds tokens left-to-right through the step machine.

    Returns:
      ("CON", screen_text)
      ("END", screen_text)
      ("NEED_SUBMISSIONS", lang)
      ("NEED_ADVICE", lang)
      ("DO_SUBMIT", (lang, harvest_date, quantity_kg, maturity, has_storage))
    """
    farmer_name = farmer.get("name", "Farmer")
    lang = farmer.get("preferred_language", "en")

    # Initial machine state
    current_step = STEP_LANG
    stack: List[Tuple[str, Dict[str, Any]]] = []
    data: Dict[str, Any] = {"lang": lang}
    last_error: Optional[str] = None

    # Filter/clean tokens
    clean_tokens = [t.strip() for t in tokens] if tokens else []
    num_tokens = len(clean_tokens)

    for i, token in enumerate(clean_tokens):
        is_last = (i == num_tokens - 1)

        # ── Handle Back ("0") ────────────────────────────────────────────────
        if token == "0":
            if current_step in (STEP_LANG, STEP_MAIN):
                # No back from language selection or main menu
                if is_last:
                    last_error = _t(lang, "Invalid choice. Please try again.", "Wahisemo nabi. Ongera ugerageze.")
                continue
            else:
                # Pop previous state
                if stack:
                    prev_step, prev_data = stack.pop()
                    current_step = prev_step
                    data = prev_data.copy()
                    lang = data.get("lang", lang)
                if is_last:
                    last_error = None
                continue

        # ── Step-Specific Token Processing ───────────────────────────────────
        if current_step == STEP_LANG:
            if token in ("1", "2"):
                stack.append((current_step, data.copy()))
                lang = "en" if token == "1" else "rw"
                data["lang"] = lang
                current_step = STEP_MAIN
                if is_last:
                    last_error = None
            else:
                if is_last:
                    last_error = _t(lang, "Invalid choice. Please try again.", "Wahisemo nabi. Ongera ugerageze.")

        elif current_step == STEP_MAIN:
            if token == "1":
                stack.append((current_step, data.copy()))
                current_step = STEP_DATE
                if is_last:
                    last_error = None
            elif token == "2":
                return "NEED_SUBMISSIONS", lang
            elif token == "3":
                return "NEED_ADVICE", lang
            else:
                if is_last:
                    last_error = _t(lang, "Invalid choice. Please try again.", "Wahisemo nabi. Ongera ugerageze.")

        elif current_step == STEP_DATE:
            cand_date, err_code = parse_harvest_date(token, get_today_kigali())
            if cand_date is not None:
                stack.append((current_step, data.copy()))
                data["harvest_date"] = cand_date
                current_step = STEP_QTY
                if is_last:
                    last_error = None
            else:
                if is_last:
                    if err_code == "BAD_CALENDAR":
                        last_error = _t(lang, "That date does not exist.", "Iyo tariki ntibaho.")
                    elif err_code == "PAST":
                        last_error = _t(lang, "That date is in the past.", "Iyo tariki yararenze.")
                    elif err_code == "TOO_FAR":
                        last_error = _t(lang, "Date is too far ahead.", "Iyo tariki iri kure cyane.")
                    else:  # BAD_FORMAT
                        last_error = _t(lang, "Invalid date. Use DD-MM-YYYY.", "Itariki siyo. Koresha DD-MM-YYYY.")

        elif current_step == STEP_QTY:
            if _is_strictly_digits(token):
                q_val = int(token)
                if 1 <= q_val <= int(MAX_QUANTITY_KG):
                    stack.append((current_step, data.copy()))
                    data["quantity_kg"] = Decimal(q_val)
                    current_step = STEP_MATURITY
                    if is_last:
                        last_error = None
                else:
                    if is_last:
                        last_error = _t(
                            lang,
                            f"Enter quantity (1-{int(MAX_QUANTITY_KG):,}kg).",
                            f"Injiza ingano (1-{int(MAX_QUANTITY_KG):,}kg).",
                        )
            else:
                if is_last:
                    last_error = _t(
                        lang,
                        f"Enter quantity (1-{int(MAX_QUANTITY_KG):,}kg).",
                        f"Injiza ingano (1-{int(MAX_QUANTITY_KG):,}kg).",
                    )

        elif current_step == STEP_MATURITY:
            mat = _RIPENESS_MAP.get(token)
            if mat:
                stack.append((current_step, data.copy()))
                data["maturity"] = mat
                current_step = STEP_STORAGE
                if is_last:
                    last_error = None
            else:
                if is_last:
                    last_error = _t(lang, "Invalid choice. Please try again.", "Wahisemo nabi. Ongera ugerageze.")

        elif current_step == STEP_STORAGE:
            if token in ("1", "2"):
                stack.append((current_step, data.copy()))
                data["has_storage"] = (token == "1")
                current_step = STEP_CONFIRM
                if is_last:
                    last_error = None
            else:
                if is_last:
                    last_error = _t(lang, "Invalid choice. Please try again.", "Wahisemo nabi. Ongera ugerageze.")

        elif current_step == STEP_CONFIRM:
            if token == "1":
                # Final confirmation choice
                return "DO_SUBMIT", (
                    lang,
                    data["harvest_date"],
                    data["quantity_kg"],
                    data["maturity"],
                    data["has_storage"],
                )
            elif token == "2":
                return "END", screen_cancelled(lang)
            else:
                if is_last:
                    last_error = _t(lang, "Invalid choice. Please try again.", "Wahisemo nabi. Ongera ugerageze.")

    # ── Render Current Screen ────────────────────────────────────────────────
    if current_step == STEP_LANG:
        return "CON", screen_language(last_error)

    if current_step == STEP_MAIN:
        return "CON", screen_main(lang, farmer_name, last_error)

    if current_step == STEP_DATE:
        return "CON", screen_ask_date(lang, get_today_kigali(), last_error)

    if current_step == STEP_QTY:
        return "CON", screen_ask_quantity(lang, data.get("harvest_date"), last_error)

    if current_step == STEP_MATURITY:
        return "CON", screen_ask_maturity(lang, last_error)

    if current_step == STEP_STORAGE:
        return "CON", screen_ask_storage(lang, last_error)

    if current_step == STEP_CONFIRM:
        return "CON", screen_confirm(
            lang,
            data["harvest_date"],
            data["quantity_kg"],
            data["maturity"],
            data["has_storage"],
            last_error,
        )

    return "END", screen_service_error()

