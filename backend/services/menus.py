# REVIEW: Kinyarwanda needs a native speaker review before demo.
"""
METLINK USSD Menus and Stateless Flow Engine.

Implements a pure function handle(tokens, farmer) -> (kind, message)
where kind is 'CON' or 'END'. All screen strings are in this module.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from backend.services.engine import MAX_QUANTITY_KG, ALLOWED_MATURITY, MAX_DAYS_AHEAD

USSD_MAX_CHARS = 182  # Africa's Talking hard maximum

# ── Fit helper ──────────────────────────────────────────────────────────────

def fit(text: str, budget: int) -> str:
    """Truncate a dynamic value to `budget` characters, adding '…' if cut."""
    if len(text) <= budget:
        return text
    return text[: budget - 1] + "~"


# ── Bilingual strings ────────────────────────────────────────────────────────

def _t(lang: str, en: str, rw: str) -> str:
    return rw if lang == "rw" else en


def screen_language() -> str:
    return "METLINK\n1. English\n2. Kinyarwanda"


def screen_invalid_language(lang: str) -> str:
    return _t(lang,
        "Invalid choice.\nMETLINK\n1. English\n2. Kinyarwanda",
        "Hitamo nabi.\nMETLINK\n1. English\n2. Kinyarwanda",
    )


def screen_main(lang: str, name: str) -> str:
    short = fit(name, 20)
    return _t(lang,
        f"Hello {short}\n1. Submit harvest\n2. My submissions\n3. My advice",
        f"Muraho {short}\n1. Ohereza umusaruro\n2. Ibyanjye\n3. Inama zanjye",
    )


def screen_invalid_main(lang: str, name: str) -> str:
    short = fit(name, 14)
    return _t(lang,
        f"Invalid. Hello {short}\n1. Submit harvest\n2. My submissions\n3. My advice",
        f"Ntibishoboka. {short}\n1. Ohereza\n2. Ibyanjye\n3. Inama",
    )


def screen_ask_date(lang: str) -> str:
    example = (date.today()).strftime("%d%m%Y")
    return _t(lang,
        f"Enter harvest date (DDMMYYYY)\neg: {example}\n0. Back",
        f"Injiza itariki y'isarura (DDMMYYYY)\nns: {example}\n0. Subira",
    )


def screen_bad_date(lang: str, reason: str) -> str:
    example = date.today().strftime("%d%m%Y")
    return _t(lang,
        f"{reason}\nDate (DDMMYYYY) eg: {example}\n0. Back",
        f"{reason}\nItariki (DDMMYYYY) ns: {example}\n0. Subira",
    )


def screen_ask_quantity(lang: str) -> str:
    return _t(lang,
        "Quantity in kg (whole number)\neg: 500\n0. Back",
        "Ingano muri kg (umubare wuzuye)\nns: 500\n0. Subira",
    )


def screen_bad_quantity(lang: str, reason: str) -> str:
    return _t(lang,
        f"{reason}\nQuantity in kg (whole number)\n0. Back",
        f"{reason}\nIngano muri kg\n0. Subira",
    )


def screen_ask_ripeness(lang: str) -> str:
    return _t(lang,
        "Tomato ripeness:\n1. Green\n2. Turning\n3. Ripe\n0. Back",
        "Ibara ry'inyanya:\n1. Ntimera\n2. Rinda\n3. Imeze\n0. Subira",
    )


def screen_bad_ripeness(lang: str) -> str:
    return _t(lang,
        "Invalid. Ripeness:\n1. Green\n2. Turning\n3. Ripe\n0. Back",
        "Ntibishoboka:\n1. Ntimera\n2. Rinda\n3. Imeze\n0. Subira",
    )


def screen_ask_storage(lang: str) -> str:
    return _t(lang,
        "Safe storage available?\n(Cool, ventilated place)\n1. Yes\n2. No\n0. Back",
        "Ufite aho ubika?\n(Ahantu hateye ubushyuhe nkeya)\n1. Yego\n2. Oya\n0. Subira",
    )


def screen_bad_storage(lang: str) -> str:
    return _t(lang,
        "Invalid. Storage available?\n1. Yes\n2. No\n0. Back",
        "Ntibishoboka. Ufite aho ubika?\n1. Yego\n2. Oya\n0. Subira",
    )


def _maturity_label(lang: str, mat: str) -> str:
    labels = {
        "GREEN":   _t(lang, "Green",   "Ntimera"),
        "TURNING": _t(lang, "Turning", "Rinda"),
        "RIPE":    _t(lang, "Ripe",    "Imeze"),
    }
    return labels.get(mat, mat)


def _action_label(lang: str, action: str, days: Optional[int]) -> str:
    if action == "SELL_NOW":
        return _t(lang, "Sell now", "Gurisha ubu")
    if action == "STORE_AND_WAIT":
        d = days or 0
        return _t(lang, f"Store {d}d", f"Bika {d}d")
    return _t(lang, "Alt market", "Soko rindi")


def screen_confirm(
    lang: str,
    harvest_date: date,
    quantity_kg: Decimal,
    maturity: str,
    has_storage: bool,
) -> str:
    date_str = harvest_date.strftime("%d/%m/%Y")
    mat = _maturity_label(lang, maturity)
    stor = _t(lang, "Yes" if has_storage else "No", "Yego" if has_storage else "Oya")
    return _t(lang,
        f"Confirm:\nDate: {date_str}\nQty: {int(quantity_kg)}kg\n"
        f"Type: {mat}\nStorage: {stor}\n1. Confirm\n2. Cancel",
        f"Emeza:\nItariki: {date_str}\nIngano: {int(quantity_kg)}kg\n"
        f"Ubwoko: {mat}\nAho kubika: {stor}\n1. Emeza\n2. Hagarika",
    )


def screen_cancelled(lang: str) -> str:
    return _t(lang,
        "Cancelled. Nothing was saved.",
        "Byahagaritswe. Nta kintu cyabitswe.",
    )


def screen_result(
    lang: str,
    action: str,
    waiting_period_days: Optional[int],
    best_market_name: Optional[str],
    best_market_price: Optional[Any],
) -> str:
    action_lbl = _action_label(lang, action, waiting_period_days)
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
    return _t(lang,
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
        mat = _maturity_label(lang, r["tomato_maturity"])
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
        act = _action_label(lang, r["action"], r.get("waiting_period_days"))
        lines.append(f"{date_str} {act}")
    return "\n".join(lines)


def screen_service_error() -> str:
    return "Service error. Try again later. / Habaye ikibazo. Ongera ugerageze nyuma."


def screen_not_registered() -> str:
    return (
        "This number is not registered. "
        "Contact your field administrator. / "
        "Iyi nimero ntiyanditswe. "
        "Vugana n'umukozi ugufasha kwandikisha."
    )


def screen_inactive() -> str:
    return (
        "Account inactive. Contact your administrator. / "
        "Konti yawe irahagaritswe. Vugana n'umuyobozi."
    )


# ── Date parsing helper ──────────────────────────────────────────────────────

def parse_ddmmyyyy(raw: str) -> Tuple[Optional[date], Optional[str]]:
    """
    Parse DDMMYYYY string. Returns (date, None) or (None, error_msg).
    """
    raw = raw.strip()
    if not raw.isdigit() or len(raw) != 8:
        return None, "Format: DDMMYYYY (8 digits)."
    try:
        d = datetime.strptime(raw, "%d%m%Y").date()
    except ValueError:
        return None, "Invalid calendar date."
    return d, None


# ── MATURITY MAP ─────────────────────────────────────────────────────────────

_RIPENESS_MAP = {"1": "GREEN", "2": "TURNING", "3": "RIPE"}

# ── Pure stateless flow ──────────────────────────────────────────────────────

def handle(tokens: List[str], farmer: Dict[str, Any]) -> Tuple[str, str]:
    """
    Stateless USSD flow engine.

    tokens  = text.split("*") if text else []
    farmer  = dict from get_farmer_by_phone, with 'preferred_language' set.

    Returns (kind, message) where kind is 'CON' or 'END'.

    Token positions:
      [0]  language choice (1=en, 2=rw)
      [1]  main menu choice (1=submit, 2=submissions, 3=advice)
      [2]  date DDMMYYYY         (submit step 1)
      [3]  quantity kg            (submit step 2)
      [4]  ripeness (1/2/3)      (submit step 3)
      [5]  storage (1/2)         (submit step 4)
      [6]  confirm (1/2)         (submit step 5)

    '0' at any depth goes back one level (reduces token depth by 1).
    """
    lang = farmer.get("preferred_language", "en")

    # ── Screen 0: language not yet chosen ────────────────────────────────────
    if not tokens or tokens[0] == "":
        return "CON", screen_language()

    t0 = tokens[0].strip()

    # ── Screen 1: language selection ─────────────────────────────────────────
    if t0 == "1":
        lang = "en"
    elif t0 == "2":
        lang = "rw"
    else:
        return "CON", screen_invalid_language(lang)

    # ── Screen 2: main menu ───────────────────────────────────────────────────
    if len(tokens) == 1:
        return "CON", screen_main(lang, farmer["name"])

    t1 = tokens[1].strip()

    if t1 == "0":
        return "CON", screen_language()

    if t1 == "2":
        # My submissions — leaf node, returned by caller using DB
        return "NEED_SUBMISSIONS", lang  # type: ignore[return-value]

    if t1 == "3":
        # My advice — leaf node, returned by caller using DB
        return "NEED_ADVICE", lang  # type: ignore[return-value]

    if t1 != "1":
        return "CON", screen_invalid_main(lang, farmer["name"])

    # ── Submit harvest flow ────────────────────────────────────────────────────
    # Step 1 – date
    if len(tokens) == 2:
        return "CON", screen_ask_date(lang)

    t2 = tokens[2].strip()
    if t2 == "0":
        return "CON", screen_main(lang, farmer["name"])

    parsed_date, date_err = parse_ddmmyyyy(t2)
    if date_err:
        return "CON", screen_bad_date(lang, date_err)

    # Date must be today or later (past check deferred so test date shifts don't break nav)
    if parsed_date < date.today():
        return "CON", screen_bad_date(lang, _t(lang, "Date is in the past.", "Itariki irashize."))

    if parsed_date > date.today() + timedelta(days=MAX_DAYS_AHEAD):
        return "CON", screen_bad_date(
            lang,
            _t(lang, f"Date too far (max {MAX_DAYS_AHEAD}d).", f"Itariki ni kure cyane (max {MAX_DAYS_AHEAD}d)."),
        )

    # Step 2 – quantity
    if len(tokens) == 3:
        return "CON", screen_ask_quantity(lang)

    t3 = tokens[3].strip()
    if t3 == "0":
        return "CON", screen_ask_date(lang)

    try:
        qty_raw = int(t3)
    except ValueError:
        return "CON", screen_bad_quantity(lang, _t(lang, "Enter a whole number.", "Injiza umubare wuzuye."))

    if qty_raw <= 0:
        return "CON", screen_bad_quantity(lang, _t(lang, "Must be > 0.", "Agomba kurenga 0."))

    if qty_raw > int(MAX_QUANTITY_KG):
        return "CON", screen_bad_quantity(
            lang,
            _t(lang, f"Max {int(MAX_QUANTITY_KG):,}kg.", f"Max {int(MAX_QUANTITY_KG):,}kg."),
        )

    quantity_kg = Decimal(qty_raw)

    # Step 3 – ripeness
    if len(tokens) == 4:
        return "CON", screen_ask_ripeness(lang)

    t4 = tokens[4].strip()
    if t4 == "0":
        return "CON", screen_ask_quantity(lang)

    maturity = _RIPENESS_MAP.get(t4)
    if maturity is None:
        return "CON", screen_bad_ripeness(lang)

    # Step 4 – storage
    if len(tokens) == 5:
        return "CON", screen_ask_storage(lang)

    t5 = tokens[5].strip()
    if t5 == "0":
        return "CON", screen_ask_ripeness(lang)

    if t5 == "1":
        has_storage = True
    elif t5 == "2":
        has_storage = False
    else:
        return "CON", screen_bad_storage(lang)

    # Step 5 – confirm
    if len(tokens) == 6:
        return "CON", screen_confirm(lang, parsed_date, quantity_kg, maturity, has_storage)

    t6 = tokens[6].strip()
    if t6 == "0":
        return "CON", screen_ask_storage(lang)

    if t6 == "2":
        return "END", screen_cancelled(lang)

    if t6 != "1":
        return "CON", screen_confirm(lang, parsed_date, quantity_kg, maturity, has_storage)

    # Signal to route handler to run process_harvest
    return "DO_SUBMIT", (lang, parsed_date, quantity_kg, maturity, has_storage)  # type: ignore[return-value]
