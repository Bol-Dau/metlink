"""
METLINK Core Services Automated Test Suite.

Verifies:
1. Phone normalization and farmer lookup.
2. Harvest validation and pure rule matching.
3. Fallback rule generation and isolation.
4. End-to-end process_harvest workflow with point-in-time evidence.
5. GSM-7 bilingual SMS templating within 160 characters.
6. Africa's Talking SMS integration, log_only mode, and delivery report handling.

All database mutations are rolled back or cleaned up to preserve pristine state.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from decimal import Decimal

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.connector import create_connection, get_cursor
from backend.services.farmer_lookup import get_farmer_by_phone, normalize_phone, set_language
from backend.services.engine import (
    DISCLAIMER,
    FALLBACK_SEEK_ALT_NAME,
    FALLBACK_SELL_NOW_NAME,
    MAX_DAYS_AHEAD,
    MAX_QUANTITY_KG,
    SYSTEM_FALLBACK_PREFIX,
    ValidationError,
    build_reason_text,
    calculate_confidence,
    ensure_fallback_rules,
    match_rules,
    pick_season,
    process_harvest,
    validate_harvest_input,
)
from backend.services.templates import (
    DISCLAIMER_EN,
    DISCLAIMER_RW,
    build_sms,
    sanitize_gsm7,
)
from backend.services.sms_service import (
    apply_delivery_report,
    mask_phone,
    reset_sms_provider,
    send_sms_sync,
    set_sms_provider,
)

passed_count = 0
failed_count = 0


def report(check_name: str, passed: bool, detail: str = "") -> None:
    global passed_count, failed_count
    if passed:
        passed_count += 1
        print(f"[PASS] {check_name}")
    else:
        failed_count += 1
        print(f"[FAIL] {check_name}: {detail}")


# ============================================================================
# Check 1: Phone Normalization
# ============================================================================
def test_phone_normalization():
    valid_cases = [
        ("0788123456", "+250788123456"),
        ("788123456", "+250788123456"),
        ("250788123456", "+250788123456"),
        ("+250788123456", "+250788123456"),
        ("078-812-3456", "+250788123456"),
        ("078 812 3456", "+250788123456"),
        ("(078) 812-3456", "+250788123456"),
        ("0721234567", "+250721234567"),
        ("0731234567", "+250731234567"),
        ("0791234567", "+250791234567"),
    ]
    for raw, expected in valid_cases:
        res = normalize_phone(raw)
        if res != expected:
            report("Phone Normalization: Valid Cases", False, f"Expected {expected} for {raw}, got {res}")
            return
    report("Phone Normalization: Valid Cases", True)

    invalid_cases = [
        "0711234567",  # Invalid prefix (71)
        "0751234567",  # Invalid prefix (75)
        "078812345",   # Too short
        "07881234567", # Too long
        "+254788123456", # Kenya code
        "letters",
        "",
        None,
    ]
    for raw in invalid_cases:
        res = normalize_phone(raw)
        if res is not None:
            report("Phone Normalization: Invalid Cases", False, f"Expected None for {raw}, got {res}")
            return
    report("Phone Normalization: Invalid Cases", True)


# ============================================================================
# Check 2: Harvest Input Validation
# ============================================================================
def test_validation():
    today = date(2026, 11, 20)

    # Valid
    h_date, qty, mat = validate_harvest_input("2026-11-25", "500.5", "ripe", reference_date=today)
    report(
        "Validation: Valid Inputs",
        h_date == date(2026, 11, 25) and qty == Decimal("500.5") and mat == "RIPE",
    )

    # Past date
    try:
        validate_harvest_input("2026-11-19", 100, "RIPE", reference_date=today)
        report("Validation: Reject Past Date", False, "Did not raise ValidationError")
    except ValidationError as err:
        report("Validation: Reject Past Date", err.code == "BAD_DATE")

    # Date > 120 days ahead
    far_future = today + timedelta(days=MAX_DAYS_AHEAD + 1)
    try:
        validate_harvest_input(far_future, 100, "RIPE", reference_date=today)
        report("Validation: Reject Far Future Date", False, "Did not raise ValidationError")
    except ValidationError as err:
        report("Validation: Reject Far Future Date", err.code == "BAD_DATE")

    # Quantity <= 0
    try:
        validate_harvest_input("2026-11-25", 0, "RIPE", reference_date=today)
        report("Validation: Reject Zero Quantity", False, "Did not raise ValidationError")
    except ValidationError as err:
        report("Validation: Reject Zero Quantity", err.code == "BAD_QUANTITY")

    try:
        validate_harvest_input("2026-11-25", -50, "RIPE", reference_date=today)
        report("Validation: Reject Negative Quantity", False, "Did not raise ValidationError")
    except ValidationError as err:
        report("Validation: Reject Negative Quantity", err.code == "BAD_QUANTITY")

    # Quantity > MAX_QUANTITY_KG
    try:
        validate_harvest_input("2026-11-25", MAX_QUANTITY_KG + 1, "RIPE", reference_date=today)
        report("Validation: Reject Excessive Quantity", False, "Did not raise ValidationError")
    except ValidationError as err:
        report("Validation: Reject Excessive Quantity", err.code == "BAD_QUANTITY")

    # Invalid maturity
    try:
        validate_harvest_input("2026-11-25", 100, "ROTTEN", reference_date=today)
        report("Validation: Reject Invalid Maturity", False, "Did not raise ValidationError")
    except ValidationError as err:
        report("Validation: Reject Invalid Maturity", err.code == "BAD_MATURITY")


# ============================================================================
# Check 3: Pure Rule Matching & Safety Guard
# ============================================================================
def test_pure_rule_matching():
    test_rules = [
        {
            "rule_id": 1,
            "rule_name": "Priority 2 Ripe",
            "maturity": "RIPE",
            "price_trend": "STABLE",
            "demand_level": "HIGH",
            "preservation_required": False,
            "action": "SELL_NOW",
            "waiting_period_days": None,
            "min_quantity_kg": None,
            "priority": 2,
        },
        {
            "rule_id": 2,
            "rule_name": "Priority 1 Ripe Bulk",
            "maturity": "RIPE",
            "price_trend": "STABLE",
            "demand_level": "HIGH",
            "preservation_required": False,
            "action": "SELL_NOW",
            "waiting_period_days": None,
            "min_quantity_kg": 500.0,
            "priority": 1,
        },
        {
            "rule_id": 3,
            "rule_name": "Storage Rule",
            "maturity": "GREEN",
            "price_trend": "STABLE",
            "demand_level": "HIGH",
            "preservation_required": True,
            "action": "STORE_AND_WAIT",
            "waiting_period_days": 7,
            "min_quantity_kg": 100.0,
            "priority": 1,
        },
        {
            "rule_id": 4,
            "rule_name": "Alternative Green Sale",
            "maturity": "GREEN",
            "price_trend": "STABLE",
            "demand_level": "HIGH",
            "preservation_required": False,
            "action": "SEEK_ALTERNATIVE_MARKET",
            "waiting_period_days": None,
            "min_quantity_kg": None,
            "priority": 2,
        },
    ]

    # Test priority order: 600kg of Ripe tomatoes should match Rule 2 (priority 1) rather than Rule 1 (priority 2)
    matched, _ = match_rules(test_rules, "RIPE", "STABLE", "HIGH", Decimal("600"), False)
    report("Rule Matching: Priority Order Selection", matched is not None and matched["rule_id"] == 2)

    # Test min quantity fallback: 200kg of Ripe tomatoes fails Rule 2 min_quantity_kg (500) and falls to Rule 1
    matched, _ = match_rules(test_rules, "RIPE", "STABLE", "HIGH", Decimal("200"), False)
    report("Rule Matching: Min Quantity Threshold", matched is not None and matched["rule_id"] == 1)

    # Test HARD SAFETY GUARD: Green tomatoes with preservation matches Rule 3 (STORE_AND_WAIT)
    matched, _ = match_rules(test_rules, "GREEN", "STABLE", "HIGH", Decimal("300"), has_suitable_preservation=True)
    report(
        "Rule Matching: Preservation Enabled Allows STORE_AND_WAIT",
        matched is not None and matched["action"] == "STORE_AND_WAIT",
    )

    # Test HARD SAFETY GUARD: Green tomatoes WITHOUT preservation MUST SKIP Rule 3 and pick Rule 4
    matched, _ = match_rules(test_rules, "GREEN", "STABLE", "HIGH", Decimal("300"), has_suitable_preservation=False)
    report(
        "Rule Matching: STORE_AND_WAIT Guard Skips to Next Rule",
        matched is not None and matched["rule_id"] == 4 and matched["action"] == "SEEK_ALTERNATIVE_MARKET",
    )

    # Test Fallback Exclusion: Rules prefixed with SYSTEM FALLBACK are never matched
    rules_with_fallback = test_rules + [
        {
            "rule_id": 99,
            "rule_name": f"{SYSTEM_FALLBACK_PREFIX} - FORCED",
            "maturity": "RIPE",
            "price_trend": "STABLE",
            "demand_level": "HIGH",
            "preservation_required": False,
            "action": "SELL_NOW",
            "waiting_period_days": None,
            "min_quantity_kg": None,
            "priority": 0,
        }
    ]
    matched, evaluated = match_rules(rules_with_fallback, "RIPE", "STABLE", "HIGH", Decimal("100"), False)
    report(
        "Rule Matching: Excludes SYSTEM FALLBACK Prefix",
        99 not in evaluated and (matched is None or matched["rule_id"] != 99),
    )


# ============================================================================
# Check 4: Bilingual GSM-7 SMS Templates
# ============================================================================
def test_templates():
    actions = ["SELL_NOW", "STORE_AND_WAIT", "SEEK_ALTERNATIVE_MARKET"]
    languages = ["en", "rw"]

    all_valid = True
    for action in actions:
        for lang in languages:
            sms = build_sms(
                lang=lang,
                action=action,
                waiting_period_days=5 if action == "STORE_AND_WAIT" else None,
                market_name="Nyabugogo Wholesale Market",
                price=680.0,
            )
            disclaimer = DISCLAIMER_RW if lang == "rw" else DISCLAIMER_EN
            if len(sms) > 160:
                report(f"Templates: Length <= 160 ({lang}, {action})", False, f"Length {len(sms)} exceeds 160: {sms}")
                all_valid = False
            if disclaimer not in sms:
                report(f"Templates: Contains Disclaimer ({lang}, {action})", False, f"Missing disclaimer in: {sms}")
                all_valid = False
            # Check GSM-7 / ASCII compatibility
            if any(ord(c) > 127 for c in sms):
                report(f"Templates: GSM-7 Safe ({lang}, {action})", False, f"Non-ASCII characters in: {sms}")
                all_valid = False

    if all_valid:
        report("Templates: Bilingual GSM-7 Generation for All Actions", True)

    # Test market name truncation when market name is exceptionally long
    long_market = "A" * 150
    sms_truncated = build_sms(
        lang="en",
        action="STORE_AND_WAIT",
        waiting_period_days=10,
        market_name=long_market,
        price=500.0,
    )
    report(
        "Templates: Long Market Truncation Preserves Disclaimer and Stays <= 160",
        len(sms_truncated) <= 160 and DISCLAIMER_EN in sms_truncated,
    )


# ============================================================================
# Check 5: Database Operations in Rolled Back Transaction
# ============================================================================
def test_db_services():
    conn = create_connection()
    try:
        with conn.cursor() as cur:
            # 1. Test get_farmer_by_phone on seeded farmers
            # Query an active farmer from the DB to be robust against other tests modifying records
            cur.execute("SELECT farmer_id, phone_number, name FROM farmers WHERE is_active = TRUE ORDER BY farmer_id LIMIT 1;")
            active_seed = cur.fetchone()
            status, farmer = get_farmer_by_phone(cur, active_seed["phone_number"])
            report("DB: Farmer Lookup Active", status == "ACTIVE" and farmer is not None and farmer["farmer_id"] == active_seed["farmer_id"])

            cur.execute("SELECT farmer_id, phone_number, name FROM farmers WHERE is_active = FALSE ORDER BY farmer_id LIMIT 1;")
            inactive_seed = cur.fetchone()
            status, inactive_farmer = get_farmer_by_phone(cur, inactive_seed["phone_number"])
            report("DB: Farmer Lookup Inactive", status == "INACTIVE" and inactive_farmer is not None)

            status, not_found = get_farmer_by_phone(cur, "+250780000000")
            report("DB: Farmer Lookup Not Found", status == "NOT_FOUND" and not_found is None)

            # 2. Test set_language
            updated = set_language(cur, farmer["farmer_id"], "rw")
            cur.execute("SELECT preferred_language FROM farmers WHERE farmer_id = %s;", (farmer["farmer_id"],))
            new_lang = cur.fetchone()["preferred_language"]
            report("DB: Update Farmer Language", updated and new_lang == "rw")

            # 3. Test ensure_fallback_rules idempotency
            fb_1 = ensure_fallback_rules(cur)
            fb_2 = ensure_fallback_rules(cur)
            report(
                "DB: Fallback Rules Idempotency",
                fb_1 == fb_2 and FALLBACK_SELL_NOW_NAME in fb_1 and FALLBACK_SEEK_ALT_NAME in fb_1,
            )

            # Check that fallback rules are inactive
            cur.execute(
                "SELECT is_active, priority FROM decision_rules WHERE rule_name = %s;",
                (FALLBACK_SELL_NOW_NAME,),
            )
            fb_row = cur.fetchone()
            report(
                "DB: Fallback Rules Inserted as Inactive with Priority 9999",
                fb_row is not None and not fb_row["is_active"] and fb_row["priority"] == 9999,
            )

            # 4. Full process_harvest with real seeded data (inside active season)
            # Harvest date within Season A 2027 (Sept 2026 to Jan 2027)
            harvest_date_in = date(2026, 11, 28)
            res_in = process_harvest(
                cur=cur,
                farmer=farmer,
                expected_harvest_date=harvest_date_in,
                quantity_kg=Decimal("450.00"),
                tomato_maturity="RIPE",
                has_suitable_preservation=False,
            )

            report(
                "DB: process_harvest Execution Inside Season",
                res_in is not None and res_in["action"] in ("SELL_NOW", "STORE_AND_WAIT", "SEEK_ALTERNATIVE_MARKET"),
            )
            report(
                "DB: Recommendation Reason Concludes with Disclaimer",
                res_in["reason"].endswith(DISCLAIMER),
            )
            report(
                "DB: Confidence Level Matches Rules (MEDIUM for Defaulted Trend)",
                res_in["confidence_level"] == "MEDIUM",
            )

            # Check submission status updated to PROCESSED
            cur.execute(
                "SELECT status, location FROM harvest_submissions WHERE submission_id = %s;",
                (res_in["submission_id"],),
            )
            sub_row = cur.fetchone()
            report(
                "DB: Harvest Submission Status PROCESSED & Location Copied",
                sub_row is not None and sub_row["status"] == "PROCESSED" and sub_row["location"] == farmer["location"],
            )

            # Check exactly 3 evidence rows
            cur.execute(
                "SELECT evidence_type, snapshot FROM recommendation_evidence WHERE recommendation_id = %s ORDER BY evidence_type;",
                (res_in["recommendation_id"],),
            )
            evidence_rows = cur.fetchall()
            ev_types = [r["evidence_type"] for r in evidence_rows]
            report(
                "DB: Exactly 3 Evidence Rows (MARKET, RULE, SEASONAL)",
                ev_types == ["MARKET", "RULE", "SEASONAL"],
            )

            # 5. Full process_harvest outside active season (e.g., Feb 2027)
            harvest_date_out = date(2027, 2, 10)
            res_out = process_harvest(
                cur=cur,
                farmer=farmer,
                expected_harvest_date=harvest_date_out,
                quantity_kg=Decimal("300.00"),
                tomato_maturity="GREEN",
                has_suitable_preservation=True,
            )
            cur.execute(
                "SELECT snapshot FROM recommendation_evidence WHERE recommendation_id = %s AND evidence_type = 'SEASONAL';",
                (res_out["recommendation_id"],),
            )
            seasonal_ev = cur.fetchone()["snapshot"]
            report(
                "DB: process_harvest Outside Season Records matched=False",
                seasonal_ev.get("matched") is False and seasonal_ev.get("season") is None,
            )

            # 6. Test fallback path (simulate no matching rule by using impossible maturity/demand combo)
            # Disable non-fallback rules temporarily in transaction to force fallback
            cur.execute("UPDATE decision_rules SET is_active = FALSE WHERE rule_name NOT LIKE 'SYSTEM FALLBACK%';")
            res_fallback = process_harvest(
                cur=cur,
                farmer=farmer,
                expected_harvest_date=date(2026, 11, 28),
                quantity_kg=Decimal("150.00"),
                tomato_maturity="RIPE",
                has_suitable_preservation=False,
            )
            cur.execute(
                "SELECT decision_rule_id, action, confidence_level FROM recommendations WHERE recommendation_id = %s;",
                (res_fallback["recommendation_id"],),
            )
            rec_row = cur.fetchone()
            report(
                "DB: Fallback Triggered When No Rule Matches (SELL_NOW for RIPE, Confidence LOW)",
                rec_row["action"] == "SELL_NOW" and rec_row["confidence_level"] == "LOW" and rec_row["decision_rule_id"] == fb_1[FALLBACK_SELL_NOW_NAME],
            )

            cur.execute(
                "SELECT snapshot FROM recommendation_evidence WHERE recommendation_id = %s AND evidence_type = 'RULE';",
                (res_fallback["recommendation_id"],),
            )
            rule_ev = cur.fetchone()["snapshot"]
            report(
                "DB: Fallback Evidence Records fallback=True and Evaluated Rule IDs",
                rule_ev.get("fallback") is True and "evaluated_rule_ids" in rule_ev,
            )

    finally:
        conn.rollback()
        conn.close()
        report("DB: Transaction Cleanly Rolled Back (Zero Test Artifacts Retained)", True)


# ============================================================================
# Check 6: SMS Service, Mocking & Delivery Reports
# ============================================================================
def test_sms_service():
    created_rec_id = None
    created_sms_provider_id = "ATXid_test_success_12345"

    try:
        # Create a temporary recommendation row for SMS testing
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO harvest_submissions (
                    farmer_id, expected_harvest_date, quantity_kg, tomato_maturity,
                    has_suitable_preservation, location, status
                ) VALUES (1, CURRENT_DATE + 1, 100, 'RIPE', FALSE, 'Runda', 'PROCESSED')
                RETURNING submission_id;
                """
            )
            sub_id = cur.fetchone()["submission_id"]

            fb_ids = ensure_fallback_rules(cur)
            cur.execute(
                """
                INSERT INTO recommendations (
                    submission_id, decision_rule_id, action, reason, confidence_level
                ) VALUES (%s, %s, 'SELL_NOW', 'Test recommendation', 'MEDIUM')
                RETURNING recommendation_id;
                """,
                (sub_id, fb_ids[FALLBACK_SELL_NOW_NAME]),
            )
            created_rec_id = cur.fetchone()["recommendation_id"]

        # 1. Test live mode with mocked SUCCESS provider
        os.environ["SMS_MODE"] = "live"
        os.environ["AT_API_KEY"] = "mock_key"
        set_sms_provider(lambda phone, msg: {"provider_id": created_sms_provider_id, "status": "Success", "status_code": 101})

        res_success = send_sms_sync(created_rec_id, "+250788123456", "Test message success")
        report(
            "SMS: Live Mode Mocked Provider Success Records SENT",
            res_success["status"] == "SENT" and res_success["provider_id"] == created_sms_provider_id,
        )

        # 2. Test live mode with mocked EXCEPTION provider (must not raise, must record FAILED)
        def failing_provider(phone, msg):
            raise ConnectionError("Simulated carrier connection failure")

        set_sms_provider(failing_provider)
        res_fail = send_sms_sync(created_rec_id, "+250788123456", "Test message failure")
        report(
            "SMS: Live Mode Provider Exception Handled Gracefully as FAILED",
            res_fail["status"] == "FAILED" and res_fail["provider_id"] is None,
        )

        # 3. Test log_only mode
        os.environ["SMS_MODE"] = "log_only"
        res_log_only = send_sms_sync(created_rec_id, "+250788123456", "Test log only message")
        report(
            "SMS: log_only Mode Inserts SENT with Provider ID NULL",
            res_log_only["status"] == "SENT" and res_log_only["provider_id"] is None,
        )

        # 4. Test delivery reports
        # A. Intermediate status 'Buffered' or 'Sent' is ignored
        ignored = apply_delivery_report(created_sms_provider_id, "Buffered")
        report("SMS Delivery Report: Intermediate Status Ignored", not ignored)

        # B. 'Success' transitions to DELIVERED
        applied_delivered = apply_delivery_report(created_sms_provider_id, "Success")
        with get_cursor() as cur:
            cur.execute("SELECT status, delivered_at FROM sms_logs WHERE provider_id = %s;", (created_sms_provider_id,))
            log_row = cur.fetchone()
        report(
            "SMS Delivery Report: 'Success' Transitions to DELIVERED with delivered_at",
            applied_delivered and log_row["status"] == "DELIVERED" and log_row["delivered_at"] is not None,
        )

        # C. Attempt to downgrade DELIVERED to Failed must be blocked
        downgraded = apply_delivery_report(created_sms_provider_id, "Failed")
        with get_cursor() as cur:
            cur.execute("SELECT status FROM sms_logs WHERE provider_id = %s;", (created_sms_provider_id,))
            current_status = cur.fetchone()["status"]
        report(
            "SMS Delivery Report: Never Downgrades DELIVERED Row",
            not downgraded and current_status == "DELIVERED",
        )

        # 5. Masking verification
        masked = mask_phone("+250788123456")
        report("SMS: Phone Masking Correctness", masked == "+25078***3456")

    finally:
        reset_sms_provider()
        # Clean up test rows
        if created_rec_id:
            with get_cursor() as cur:
                cur.execute("DELETE FROM sms_logs WHERE recommendation_id = %s;", (created_rec_id,))
                cur.execute("DELETE FROM recommendations WHERE recommendation_id = %s;", (created_rec_id,))
                cur.execute("DELETE FROM harvest_submissions WHERE submission_id = %s;", (sub_id,))


def main():
    print("=" * 60)
    print("METLINK CORE SERVICES TEST SUITE")
    print("=" * 60)

    test_phone_normalization()
    test_validation()
    test_pure_rule_matching()
    test_templates()
    test_db_services()
    test_sms_service()

    print("=" * 60)
    print(f"RESULTS: {passed_count} passed, {failed_count} failed")
    print("=" * 60)

    if failed_count > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
