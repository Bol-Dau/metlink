"""
METLINK Harvest Coordination Engine.

Evaluates farmer harvest submissions against active market conditions,
agricultural seasons, and decision rules to generate actionable advice.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from psycopg.types.json import Jsonb

logger = logging.getLogger(__name__)

# Engine Constants
MAX_DAYS_AHEAD: int = 120
MAX_QUANTITY_KG: float = 100000.0

ALLOWED_MATURITY = {"GREEN", "TURNING", "RIPE"}
ALLOWED_ACTIONS = {"SELL_NOW", "STORE_AND_WAIT", "SEEK_ALTERNATIVE_MARKET"}
ALLOWED_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}

# Market & Rule Constants
DEFAULT_PRICE_TREND: str = "STABLE"
SYSTEM_FALLBACK_PREFIX: str = "SYSTEM FALLBACK"
FALLBACK_SELL_NOW_NAME: str = "SYSTEM FALLBACK - SELL NOW"
FALLBACK_SEEK_ALT_NAME: str = "SYSTEM FALLBACK - SEEK ALTERNATIVE MARKET"

DISCLAIMER: str = "This is decision support only and does not guarantee prices, buyers, or income."


class ValidationError(Exception):
    """Raised when harvest input fails validation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ============================================================================
# Pure Helpers (no DB access, easily testable)
# ============================================================================

def parse_date(value: Any) -> date:
    """Coerce string or date to datetime.date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    raise ValueError(f"Cannot parse date from {value!r}")


def validate_harvest_input(
    expected_harvest_date: Any,
    quantity_kg: Any,
    tomato_maturity: str,
    reference_date: Optional[date] = None,
) -> Tuple[date, Decimal, str]:
    """
    Validates harvest submission inputs.

    Raises ValidationError with code 'BAD_DATE', 'BAD_QUANTITY', or 'BAD_MATURITY'.
    """
    ref = reference_date or date.today()

    # 1. Date validation
    try:
        harvest_date = parse_date(expected_harvest_date)
    except Exception as exc:
        raise ValidationError("BAD_DATE", f"Invalid date format: {exc}") from exc

    if harvest_date < ref:
        raise ValidationError("BAD_DATE", "Harvest date cannot be in the past.")

    max_date = ref + timedelta(days=MAX_DAYS_AHEAD)
    if harvest_date > max_date:
        raise ValidationError(
            "BAD_DATE",
            f"Harvest date cannot be more than {MAX_DAYS_AHEAD} days ahead.",
        )

    # 2. Quantity validation
    try:
        qty = Decimal(str(quantity_kg))
    except Exception as exc:
        raise ValidationError("BAD_QUANTITY", f"Invalid quantity: {exc}") from exc

    if qty <= Decimal("0"):
        raise ValidationError("BAD_QUANTITY", "Quantity must be greater than zero.")

    if qty > Decimal(str(MAX_QUANTITY_KG)):
        raise ValidationError(
            "BAD_QUANTITY",
            f"Quantity exceeds maximum allowed ({MAX_QUANTITY_KG:,.0f} kg).",
        )

    # 3. Maturity validation
    mat = str(tomato_maturity).strip().upper()
    if mat not in ALLOWED_MATURITY:
        raise ValidationError(
            "BAD_MATURITY",
            f"Invalid maturity '{tomato_maturity}': must be one of {sorted(ALLOWED_MATURITY)}.",
        )

    return harvest_date, qty, mat


def pick_season(seasons: List[Dict[str, Any]], harvest_date: date) -> Optional[Dict[str, Any]]:
    """
    Finds the active season whose date range encompasses the expected harvest date.
    """
    for season in seasons:
        if not season.get("is_active", True):
            continue
        start = parse_date(season["start_date"])
        end = parse_date(season["end_date"])
        if start <= harvest_date <= end:
            return season
    return None


def match_rules(
    rules: List[Dict[str, Any]],
    maturity: str,
    price_trend: str,
    demand_level: str,
    quantity_kg: Decimal,
    has_suitable_preservation: bool,
) -> Tuple[Optional[Dict[str, Any]], List[int]]:
    """
    Evaluates candidate decision rules in priority order.

    Rules are evaluated sorted by priority ASC, then rule_id ASC.
    Any rule starting with SYSTEM_FALLBACK_PREFIX is excluded.

    Safety guard:
    If a matched rule recommends STORE_AND_WAIT and the farmer has no
    suitable preservation, the rule is skipped and evaluation continues.
    """
    evaluated_ids: List[int] = []

    # Ensure rules are evaluated in deterministic priority order
    sorted_rules = sorted(
        rules,
        key=lambda r: (r.get("priority", 1), r.get("rule_id", 0)),
    )

    for rule in sorted_rules:
        rule_name = rule.get("rule_name", "")
        if rule_name.startswith(SYSTEM_FALLBACK_PREFIX):
            continue

        rule_id = rule["rule_id"]
        evaluated_ids.append(rule_id)

        # Match criteria
        if rule["maturity"] != maturity:
            continue
        if rule["price_trend"] != price_trend:
            continue
        if rule["demand_level"] != demand_level:
            continue

        # Minimum quantity check
        min_qty = rule.get("min_quantity_kg")
        if min_qty is not None and quantity_kg < Decimal(str(min_qty)):
            continue

        # Preservation requirements
        if rule.get("preservation_required") and not has_suitable_preservation:
            continue

        # HARD SAFETY GUARD: STORE_AND_WAIT requires preservation
        if rule.get("action") == "STORE_AND_WAIT" and not has_suitable_preservation:
            logger.warning(
                "Skipping rule %s (%s): STORE_AND_WAIT not permitted without suitable preservation.",
                rule_id,
                rule_name,
            )
            continue

        # Final verification
        if rule.get("action") == "STORE_AND_WAIT" and not has_suitable_preservation:
            raise RuntimeError("Safety guard violated: STORE_AND_WAIT without preservation.")

        return rule, evaluated_ids

    return None, evaluated_ids


def calculate_confidence(
    has_matched_rule: bool,
    has_matched_season: bool,
    trend_source: str,
) -> str:
    """
    Computes confidence level:
    - LOW: fallback recommendation (no rule matched)
    - MEDIUM: rule matched but season is missing or trend was defaulted
    - HIGH: rule matched, season matched, and trend is from real market data
    """
    if not has_matched_rule:
        return "LOW"
    if not has_matched_season or trend_source == "default":
        return "MEDIUM"
    return "HIGH"


def build_reason_text(
    action: str,
    rule_name: Optional[str],
    maturity: str,
    demand_level: Optional[str],
    price_trend: str,
    best_market_name: Optional[str],
    best_market_price: Optional[Decimal],
    waiting_period_days: Optional[int],
    is_fallback: bool,
) -> str:
    """
    Constructs a factual explanation stored in recommendations.reason.
    Always concludes with the mandatory non-guarantee disclaimer.
    """
    trend_note = "Price trend is not available and is assumed stable."

    if is_fallback:
        return (
            f"No specific decision rule matched your harvest criteria ({maturity} maturity). "
            f"{trend_note} Conservative advisory: {action}. Administrators will review rules. "
            f"{DISCLAIMER}"
        )

    market_part = ""
    if best_market_name and best_market_price is not None:
        market_part = f" Top market is {best_market_name} ({float(best_market_price):,.2f} RWF/kg, demand {demand_level})."

    waiting_part = ""
    if action == "STORE_AND_WAIT" and waiting_period_days:
        waiting_part = f" for {waiting_period_days} days"

    return (
        f"Advised {action}{waiting_part} under rule '{rule_name}' for {maturity} tomatoes.{market_part} "
        f"{trend_note} {DISCLAIMER}"
    )


# ============================================================================
# Database Operations (takes cursor from caller, never commits)
# ============================================================================

def ensure_fallback_rules(cur: Any) -> Dict[str, int]:
    """
    Idempotent helper that ensures reserved fallback rules exist in decision_rules.
    Runs inside the caller's transaction and NEVER commits.

    Creates whichever is missing:
    - 'SYSTEM FALLBACK - SELL NOW' (action SELL_NOW)
    - 'SYSTEM FALLBACK - SEEK ALTERNATIVE MARKET' (action SEEK_ALTERNATIVE_MARKET)

    Both are inactive (is_active = FALSE), priority 9999, preservation_required = FALSE.
    Returns mapping of rule_name -> rule_id.
    """
    cur.execute(
        """
        SELECT rule_id, rule_name
        FROM decision_rules
        WHERE rule_name IN (%s, %s);
        """,
        (FALLBACK_SELL_NOW_NAME, FALLBACK_SEEK_ALT_NAME),
    )
    rows = cur.fetchall()
    existing = {row["rule_name"]: row["rule_id"] for row in rows}

    if FALLBACK_SELL_NOW_NAME not in existing:
        cur.execute(
            """
            INSERT INTO decision_rules (
                rule_name, maturity, price_trend, demand_level,
                preservation_required, action, waiting_period_days,
                min_quantity_kg, priority, is_active, created_at, updated_at
            )
            VALUES (
                %s, 'RIPE', 'STABLE', 'HIGH',
                FALSE, 'SELL_NOW', NULL,
                NULL, 9999, FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING rule_id;
            """,
            (FALLBACK_SELL_NOW_NAME,),
        )
        existing[FALLBACK_SELL_NOW_NAME] = cur.fetchone()["rule_id"]

    if FALLBACK_SEEK_ALT_NAME not in existing:
        cur.execute(
            """
            INSERT INTO decision_rules (
                rule_name, maturity, price_trend, demand_level,
                preservation_required, action, waiting_period_days,
                min_quantity_kg, priority, is_active, created_at, updated_at
            )
            VALUES (
                %s, 'GREEN', 'STABLE', 'LOW',
                FALSE, 'SEEK_ALTERNATIVE_MARKET', NULL,
                NULL, 9999, FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING rule_id;
            """,
            (FALLBACK_SEEK_ALT_NAME,),
        )
        existing[FALLBACK_SEEK_ALT_NAME] = cur.fetchone()["rule_id"]

    return existing


def process_harvest(
    cur: Any,
    farmer: Dict[str, Any],
    expected_harvest_date: Any,
    quantity_kg: Any,
    tomato_maturity: str,
    has_suitable_preservation: bool,
) -> Dict[str, Any]:
    """
    Executes the end-to-end harvest evaluation workflow inside caller's transaction.

    1. Idempotently ensures fallback rules exist.
    2. Validates harvest parameters.
    3. Inserts harvest_submissions (status 'PENDING', location from farmer).
    4. Evaluates active seasons and markets.
    5. Evaluates decision rules (with preservation safety guard).
    6. Inserts recommendations with matching or fallback decision rule.
    7. Inserts 3 point-in-time evidence snapshots (MARKET, SEASONAL, RULE).
    8. Updates harvest_submissions status to 'PROCESSED'.

    Returns summary dictionary. NEVER commits.
    """
    farmer_id = farmer["farmer_id"]
    farmer_location = farmer["location"]

    # 1. Fallback rules guarantee
    fallback_ids = ensure_fallback_rules(cur)

    # 2. Input validation
    harvest_date, qty, maturity = validate_harvest_input(
        expected_harvest_date, quantity_kg, tomato_maturity
    )

    # 3. Create harvest submission
    cur.execute(
        """
        INSERT INTO harvest_submissions (
            farmer_id, expected_harvest_date, quantity_kg,
            tomato_maturity, has_suitable_preservation, location, status, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', CURRENT_TIMESTAMP)
        RETURNING submission_id;
        """,
        (farmer_id, harvest_date, qty, maturity, bool(has_suitable_preservation), farmer_location),
    )
    submission_id = cur.fetchone()["submission_id"]

    # 4. Active agricultural season
    cur.execute(
        """
        SELECT season_id, season_name, start_date, end_date, description, is_active
        FROM seasonal_information
        WHERE is_active = TRUE
          AND %s >= start_date AND %s <= end_date
        ORDER BY season_id DESC
        LIMIT 1;
        """,
        (harvest_date, harvest_date),
    )
    season_row = cur.fetchone()
    season = dict(season_row) if season_row else None

    # 5. Market context
    # Note: price = highest average_price_per_kg among active markets;
    # demand = the demand_level of that same highest-price market.
    cur.execute(
        """
        SELECT market_id, market_name, location, average_price_per_kg, demand_level, source, is_active
        FROM market_information
        WHERE is_active = TRUE
        ORDER BY average_price_per_kg DESC, market_id ASC;
        """
    )
    active_markets = [dict(r) for r in cur.fetchall()]

    top_market = active_markets[0] if active_markets else None
    best_market_price = top_market["average_price_per_kg"] if top_market else None
    best_market_demand = top_market["demand_level"] if top_market else None
    best_market_name = top_market["market_name"] if top_market else None
    price_trend = DEFAULT_PRICE_TREND
    trend_source = "default"

    # 6. Decision rules evaluation
    cur.execute(
        """
        SELECT rule_id, rule_name, maturity, price_trend, demand_level,
               preservation_required, action, waiting_period_days, min_quantity_kg,
               priority, is_active
        FROM decision_rules
        WHERE is_active = TRUE
        ORDER BY priority ASC, rule_id ASC;
        """
    )
    active_rules = [dict(r) for r in cur.fetchall()]

    matched_rule: Optional[Dict[str, Any]] = None
    evaluated_ids: List[int] = []

    if top_market is not None and best_market_demand is not None:
        matched_rule, evaluated_ids = match_rules(
            active_rules,
            maturity=maturity,
            price_trend=price_trend,
            demand_level=best_market_demand,
            quantity_kg=qty,
            has_suitable_preservation=bool(has_suitable_preservation),
        )

    # 7. Action & Confidence resolution
    if matched_rule is not None:
        is_fallback = False
        action = matched_rule["action"]
        waiting_period_days = matched_rule["waiting_period_days"]
        rule_id = matched_rule["rule_id"]
        rule_name = matched_rule["rule_name"]
    else:
        is_fallback = True
        # Engine rule 7 fallback: SELL_NOW if RIPE, otherwise SEEK_ALTERNATIVE_MARKET
        action = "SELL_NOW" if maturity == "RIPE" else "SEEK_ALTERNATIVE_MARKET"
        waiting_period_days = None
        rule_name = FALLBACK_SELL_NOW_NAME if action == "SELL_NOW" else FALLBACK_SEEK_ALT_NAME
        rule_id = fallback_ids[rule_name]

    # Re-verify safety guard
    if action == "STORE_AND_WAIT" and not has_suitable_preservation:
        raise RuntimeError("Safety guard violated: STORE_AND_WAIT cannot be issued without preservation.")

    confidence = calculate_confidence(
        has_matched_rule=(not is_fallback),
        has_matched_season=(season is not None),
        trend_source=trend_source,
    )

    reason = build_reason_text(
        action=action,
        rule_name=rule_name if not is_fallback else None,
        maturity=maturity,
        demand_level=best_market_demand,
        price_trend=price_trend,
        best_market_name=best_market_name,
        best_market_price=best_market_price,
        waiting_period_days=waiting_period_days,
        is_fallback=is_fallback,
    )

    # 8. Insert recommendation
    cur.execute(
        """
        INSERT INTO recommendations (
            submission_id, decision_rule_id, action, reason,
            waiting_period_days, confidence_level, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        RETURNING recommendation_id;
        """,
        (submission_id, rule_id, action, reason, waiting_period_days, confidence),
    )
    recommendation_id = cur.fetchone()["recommendation_id"]

    # 9. Insert 3 Evidence Rows (MARKET, SEASONAL, RULE)
    # Market evidence
    market_snapshot = {
        "active_markets": [
            {
                "market_id": m["market_id"],
                "market_name": m["market_name"],
                "location": m["location"],
                "average_price_per_kg": float(m["average_price_per_kg"]),
                "demand_level": m["demand_level"],
            }
            for m in active_markets
        ],
        "top_market": (
            {
                "market_id": top_market["market_id"],
                "market_name": top_market["market_name"],
                "average_price_per_kg": float(top_market["average_price_per_kg"]),
                "demand_level": top_market["demand_level"],
            }
            if top_market
            else None
        ),
        "trend": price_trend,
        "trend_source": trend_source,
        "taken_at": datetime.now(timezone.utc).isoformat(),
    }
    cur.execute(
        """
        INSERT INTO recommendation_evidence (
            recommendation_id, evidence_type, market_information_id,
            seasonal_information_id, decision_rule_id, snapshot, notes, created_at
        )
        VALUES (%s, 'MARKET', %s, NULL, NULL, %s, %s, CURRENT_TIMESTAMP);
        """,
        (
            recommendation_id,
            top_market["market_id"] if top_market else None,
            Jsonb(market_snapshot),
            "Market context snapshot (top price and demand with defaulted stable trend)",
        ),
    )

    # Seasonal evidence
    seasonal_snapshot = {
        "season": (
            {
                "season_id": season["season_id"],
                "season_name": season["season_name"],
                "start_date": season["start_date"].isoformat(),
                "end_date": season["end_date"].isoformat(),
            }
            if season
            else None
        ),
        "matched": season is not None,
        "reason": (
            "Harvest date falls within active season"
            if season
            else "No active season encompasses expected harvest date"
        ),
    }
    cur.execute(
        """
        INSERT INTO recommendation_evidence (
            recommendation_id, evidence_type, market_information_id,
            seasonal_information_id, decision_rule_id, snapshot, notes, created_at
        )
        VALUES (%s, 'SEASONAL', NULL, %s, NULL, %s, %s, CURRENT_TIMESTAMP);
        """,
        (
            recommendation_id,
            season["season_id"] if season else None,
            Jsonb(seasonal_snapshot),
            "Seasonal context snapshot",
        ),
    )

    # Rule evidence
    rule_snapshot = {
        "fallback": is_fallback,
        "evaluated_rule_ids": evaluated_ids,
        "matched_rule": (
            {
                "rule_id": matched_rule["rule_id"],
                "rule_name": matched_rule["rule_name"],
                "priority": matched_rule["priority"],
                "action": matched_rule["action"],
            }
            if matched_rule
            else None
        ),
    }
    cur.execute(
        """
        INSERT INTO recommendation_evidence (
            recommendation_id, evidence_type, market_information_id,
            seasonal_information_id, decision_rule_id, snapshot, notes, created_at
        )
        VALUES (%s, 'RULE', NULL, NULL, %s, %s, %s, CURRENT_TIMESTAMP);
        """,
        (
            recommendation_id,
            rule_id,
            Jsonb(rule_snapshot),
            "Rule evaluation audit trace",
        ),
    )

    # 10. Update submission status to PROCESSED
    cur.execute(
        """
        UPDATE harvest_submissions
        SET status = 'PROCESSED'
        WHERE submission_id = %s;
        """,
        (submission_id,),
    )

    return {
        "submission_id": submission_id,
        "recommendation_id": recommendation_id,
        "action": action,
        "reason": reason,
        "waiting_period_days": waiting_period_days,
        "confidence_level": confidence,
        "rule_id": rule_id,
        "best_market_name": best_market_name,
        "best_market_price": best_market_price,
        "demand_level": best_market_demand,
    }


def find_recent_duplicate(
    cur: Any,
    farmer_id: int,
    expected_harvest_date: Any,
    quantity_kg: Any,
    tomato_maturity: str,
    has_suitable_preservation: bool,
    seconds: int = 120,
) -> Optional[Dict[str, Any]]:
    """
    Returns the existing process_harvest result dict if the same farmer
    submitted the same harvest data within the last `seconds` seconds
    (default 120 s = 2 minutes).

    This is the cross-process idempotency guard against Africa's Talking
    retries and accidental double-sends. Returns None when no duplicate exists.

    The returned dict has the same keys as process_harvest's return value.
    """
    harvest_date = parse_date(expected_harvest_date)
    qty = Decimal(str(quantity_kg))
    mat = str(tomato_maturity).strip().upper()
    has_pres = bool(has_suitable_preservation)

    cur.execute(
        """
        SELECT
            s.submission_id,
            r.recommendation_id,
            r.action,
            r.reason,
            r.waiting_period_days,
            r.confidence_level,
            r.decision_rule_id  AS rule_id,
            s.location
        FROM harvest_submissions s
        JOIN recommendations r ON r.submission_id = s.submission_id
        WHERE s.farmer_id = %s
          AND s.expected_harvest_date = %s
          AND s.quantity_kg = %s
          AND s.tomato_maturity = %s
          AND s.has_suitable_preservation = %s
          AND s.created_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
        ORDER BY s.submission_id DESC
        LIMIT 1;
        """,
        (farmer_id, harvest_date, qty, mat, has_pres, seconds),
    )
    row = cur.fetchone()
    if row is None:
        return None

    # Fetch best market for display (cheapest read, no MARKET evidence join needed)
    cur.execute(
        """
        SELECT snapshot
        FROM recommendation_evidence
        WHERE recommendation_id = %s
          AND evidence_type = 'MARKET'
        LIMIT 1;
        """,
        (row["recommendation_id"],),
    )
    ev = cur.fetchone()
    best_market_name = None
    best_market_price = None
    demand_level = None
    if ev and ev["snapshot"]:
        snap = ev["snapshot"]
        top = snap.get("top_market")
        if top:
            best_market_name = top.get("market_name")
            best_market_price = top.get("average_price_per_kg")
            demand_level = top.get("demand_level")

    return {
        "submission_id": row["submission_id"],
        "recommendation_id": row["recommendation_id"],
        "action": row["action"],
        "reason": row["reason"],
        "waiting_period_days": row["waiting_period_days"],
        "confidence_level": row["confidence_level"],
        "rule_id": row["rule_id"],
        "best_market_name": best_market_name,
        "best_market_price": best_market_price,
        "demand_level": demand_level,
    }


def list_submissions(cur: Any, farmer_id: int, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Returns recent harvest submissions for a farmer, newest first.
    """
    cur.execute(
        """
        SELECT submission_id, farmer_id, expected_harvest_date, quantity_kg,
               tomato_maturity, has_suitable_preservation, location, status, created_at
        FROM harvest_submissions
        WHERE farmer_id = %s
        ORDER BY created_at DESC, submission_id DESC
        LIMIT %s;
        """,
        (farmer_id, limit),
    )
    return [dict(r) for r in cur.fetchall()]


def list_recommendations(cur: Any, farmer_id: int, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Returns recent recommendations for a farmer, newest first.
    """
    cur.execute(
        """
        SELECT r.recommendation_id, r.submission_id, r.decision_rule_id,
               r.action, r.reason, r.waiting_period_days, r.confidence_level,
               r.created_at, s.expected_harvest_date, s.quantity_kg, s.tomato_maturity
        FROM recommendations r
        JOIN harvest_submissions s ON r.submission_id = s.submission_id
        WHERE s.farmer_id = %s
        ORDER BY r.created_at DESC, r.recommendation_id DESC
        LIMIT %s;
        """,
        (farmer_id, limit),
    )
    return [dict(r) for r in cur.fetchall()]
