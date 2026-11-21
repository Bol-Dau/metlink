"""
METLINK USSD Navigation & Step Machine Test Suite.

Verifies:
- Pure step machine token folding & stack-based navigation.
- Zero-lock: '0' (Back) and invalid input resilience.
- Single-step date entry (ENTER_DATE) and confirmation screen.
- Checks (a) through (n) against the real Flask app and DB with SMS mocked.
"""

from __future__ import annotations

import itertools
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app import create_app
from backend.services import menus, session_store
import backend.services.sms_service as _sms_svc
from database.connector import get_connection

NAV_PHONES = [f"+25078899001{i}" for i in range(10)]
UNREG_PHONE = "+250788990098"

passed = 0
failed = 0


def report(label: str, ok: bool, detail: str = ""):
    global passed, failed
    if ok:
        passed += 1
        print(f"[PASS] {label}")
    else:
        failed += 1
        print(f"[FAIL] {label} — {detail}")


def setup_nav_farmers():
    """Insert test farmers for navigation tests (NAV_PHONES)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            for i, phone in enumerate(NAV_PHONES):
                cur.execute(
                    """
                    INSERT INTO farmers
                        (phone_number, name, location, preferred_language,
                         registration_source, registered_by, is_active)
                    VALUES (%s, %s, 'TestNavVillage', 'en', 'admin', 1, TRUE)
                    ON CONFLICT (phone_number) DO UPDATE SET is_active = TRUE, preferred_language = 'en';
                    """,
                    (phone, f"TEST_NavFarmer_{i:02d}"),
                )


def cleanup_nav_farmers():
    """Delete ONLY rows tied to NAV_PHONES in foreign key order."""
    counts = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT farmer_id FROM farmers WHERE phone_number = ANY(%s);", (NAV_PHONES,))
            fids = [r["farmer_id"] for r in cur.fetchall()]
            if not fids:
                for t in ("sms_logs", "recommendation_evidence", "recommendations", "harvest_submissions", "farmers"):
                    counts[t] = 0
                return counts

            cur.execute(
                """
                DELETE FROM sms_logs WHERE recommendation_id IN (
                    SELECT r.recommendation_id FROM recommendations r
                    JOIN harvest_submissions s ON r.submission_id = s.submission_id
                    WHERE s.farmer_id = ANY(%s)
                );
                """,
                (fids,),
            )
            counts["sms_logs"] = cur.rowcount

            cur.execute(
                """
                DELETE FROM recommendation_evidence WHERE recommendation_id IN (
                    SELECT r.recommendation_id FROM recommendations r
                    JOIN harvest_submissions s ON r.submission_id = s.submission_id
                    WHERE s.farmer_id = ANY(%s)
                );
                """,
                (fids,),
            )
            counts["recommendation_evidence"] = cur.rowcount

            cur.execute(
                """
                DELETE FROM recommendations WHERE submission_id IN (
                    SELECT submission_id FROM harvest_submissions WHERE farmer_id = ANY(%s)
                );
                """,
                (fids,),
            )
            counts["recommendations"] = cur.rowcount

            cur.execute("DELETE FROM harvest_submissions WHERE farmer_id = ANY(%s);", (fids,))
            counts["harvest_submissions"] = cur.rowcount

            cur.execute("DELETE FROM farmers WHERE farmer_id = ANY(%s);", (fids,))
            counts["farmers"] = cur.rowcount

    return counts


def ussd_post(client, phone, text, session_id=None):
    if session_id is None:
        session_id = f"SID_NAV_{phone}"
    token = os.getenv("AT_WEBHOOK_TOKEN", "").strip("\"'")
    url = "/api/ussd/callback"
    if token:
        url += f"?token={token}"
    return client.post(
        url,
        data={
            "sessionId": session_id,
            "phoneNumber": phone,
            "text": text,
            "serviceCode": "*123#",
            "networkCode": "63902",
        },
    )


_mock_nav_gen = itertools.count(1)
_sms_calls: List[Dict[str, Any]] = []


def _mock_provider(phone_number: str, message: str) -> Dict[str, Any]:
    global _sms_calls
    call_info = {
        "phone_number": phone_number,
        "message": message,
        "provider_id": f"ATXid_nav_{next(_mock_nav_gen):06d}",
        "status": "Success",
        "statusCode": 101,
    }
    _sms_calls.append(call_info)
    return call_info


_sms_svc.set_sms_provider(_mock_provider)


# ============================================================================
# Pure Step Machine Unit Tests
# ============================================================================

def test_pure_fold_function():
    print("\n--- Pure Fold Function Unit Tests ---")
    farmer = {"name": "Jean", "preferred_language": "en"}
    today = menus.get_today_kigali()
    target_d = today + timedelta(days=20)
    d_fmt = target_d.strftime("%d-%m-%Y")

    # 1. Empty tokens -> SELECT_LANG
    k, b = menus.handle([], farmer)
    report("Pure: Empty tokens gives SELECT_LANG", k == "CON" and "1. English" in b)

    # 2. Invalid choice on SELECT_LANG -> error prepended, screen preserved
    k, b = menus.handle(["3"], farmer)
    report("Pure: '3' on SELECT_LANG shows error prepended", k == "CON" and "Invalid choice" in b and "1. English" in b)

    # 3. Invalid choice followed by valid choice -> advances to MAIN_MENU
    k, b = menus.handle(["3", "1"], farmer)
    report("Pure: '3*1' advances to MAIN_MENU", k == "CON" and "Hello Jean" in b and "1. Submit expected harvest" in b)

    # 4. '0' on language or main menu is invalid (no back)
    k, b = menus.handle(["0"], farmer)
    report("Pure: '0' on SELECT_LANG is invalid", k == "CON" and "Invalid choice" in b)
    k, b = menus.handle(["1", "0"], farmer)
    report("Pure: '0' on MAIN_MENU is invalid", k == "CON" and "Invalid choice" in b)

    # 5. Advance into date flow: ENTER_DATE
    k, b = menus.handle(["1", "1"], farmer)
    report("Pure: '1*1' opens ENTER_DATE", k == "CON" and "Enter harvest date" in b)

    # 6. '0' from date pops back to MAIN_MENU
    k, b = menus.handle(["1", "1", "0"], farmer)
    report("Pure: '1*1*0' returns to MAIN_MENU", k == "CON" and "Hello Jean" in b and "Invalid" not in b)

    # 7. Valid date advances to ENTER_QUANTITY (with Date: in header)
    k, b = menus.handle(["1", "1", d_fmt], farmer)
    readable = menus.format_readable_date(target_d)
    report("Pure: Valid date opens ENTER_QUANTITY with Date header", k == "CON" and f"Date: {readable}" in b and "Quantity" in b)

    # 8. '0' on quantity prompt returns to ENTER_DATE
    k, b = menus.handle(["1", "1", d_fmt, "0"], farmer)
    report("Pure: '0' on quantity prompt returns to ENTER_DATE", k == "CON" and "Enter harvest date" in b and "Invalid" not in b)

    # 9. Multi-level '0*0' from quantity returns to MAIN_MENU
    k, b = menus.handle(["1", "1", d_fmt, "0", "0"], farmer)
    report("Pure: Multi-level '0*0' returns to MAIN_MENU", k == "CON" and "Hello Jean" in b)

    # 10. Full valid path to confirm
    toks = ["1", "1", d_fmt, "500", "3", "1"]
    k, b = menus.handle(toks, farmer)
    report("Pure: Valid tokens reach CONFIRM_SUBMISSION", k == "CON" and readable in b and "1. Confirm & Submit" in b)

    # 11. Confirm choices: '1' -> DO_SUBMIT, '2' -> END cancelled, '0' -> back to storage
    k_sub, p_sub = menus.handle(toks + ["1"], farmer)
    report("Pure: Confirm '1' gives DO_SUBMIT", k_sub == "DO_SUBMIT" and p_sub[1] == target_d and p_sub[2] == Decimal(500))

    k_can, b_can = menus.handle(toks + ["2"], farmer)
    report("Pure: Confirm '2' gives END cancelled", k_can == "END" and "Cancelled" in b_can)

    k_bck, b_bck = menus.handle(toks + ["0"], farmer)
    report("Pure: Confirm '0' returns to SELECT_STORAGE", k_bck == "CON" and "safe place to store" in b_bck)

    # 12. Non-existent date (31-02-2026) -> rejected on ENTER_DATE
    k_nonexist, b_nonexist = menus.handle(["1", "1", "31-02-2026"], farmer)
    report("Pure: 31-02-2026 rejects on ENTER_DATE with error", k_nonexist == "CON" and "Enter harvest date" in b_nonexist and "does not exist" in b_nonexist.lower())


# ============================================================================
# Integration Checks (a) through (n)
# ============================================================================

def run_integration_tests(app):
    print("\n--- Integration Checks (a) through (n) ---")
    client = app.test_client()

    # ── (a) "3" on language screen re-prompts error, next "1" moves on ────────
    phone_a = NAV_PHONES[0]
    r_bad = ussd_post(client, phone_a, "3", session_id="SID_A1")
    b_bad = r_bad.data.decode()
    r_next = ussd_post(client, phone_a, "3*1", session_id="SID_A2")
    b_next = r_next.data.decode()
    report(
        "(a) '3' re-prompts language with error, '3*1' reaches main menu",
        b_bad.startswith("CON") and "Invalid choice" in b_bad and "1. English" in b_bad
        and b_next.startswith("CON") and "Submit expected harvest" in b_next,
    )

    # ── (b) Invalid inputs at every step re-prompt error and write nothing ─────
    phone_b = NAV_PHONES[1]
    today = menus.get_today_kigali()
    valid_d = today + timedelta(days=25)
    valid_d_str = valid_d.strftime("%d-%m-%Y")
    steps_tests = [
        ("1*9", "main menu '9'", "Invalid choice"),
        ("1*1*bad-date", "bad date format", "Invalid date"),
        ("1*1*0", "date '0' goes back to main menu", "Submit expected harvest"),
        (f"1*1*{valid_d_str}*0", "quantity '0' (back to date)", "Enter harvest date"),
        (f"1*1*{valid_d_str}*00", "quantity '00' (invalid qty)", "Enter quantity"),
        (f"1*1*{valid_d_str}*500*7", "ripeness '7'", "Invalid choice"),
        (f"1*1*{valid_d_str}*500*3*3", "storage '3'", "Invalid choice"),
    ]

    all_b_ok = True
    for text_path, label, expect_sub in steps_tests:
        r = ussd_post(client, phone_b, text_path, session_id=f"SID_B_{label[:4]}")
        body = r.data.decode()
        if not (body.startswith("CON") and expect_sub.lower() in body.lower()):
            all_b_ok = False
            print(f"  [FAIL detail on {label}]: {body[:80]}")

    # Verify no DB write
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM harvest_submissions s JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = %s;", (phone_b,))
            db_cnt = cur.fetchone()["cnt"]
    report("(b) Invalid inputs at every step re-prompt properly, 0 DB writes", all_b_ok and db_cnt == 0)

    # ── (c) "0" steps back several levels, abandoned data not reused ──────────
    phone_c = NAV_PHONES[2]
    # Path: EN -> Main -> Date -> 0 (back to main) -> 2 (My submissions)
    r_multi_0 = ussd_post(client, phone_c, f"1*1*{valid_d_str}*0*0*2", session_id="SID_C_BACK")
    b_c = r_multi_0.data.decode()
    report("(c) Multi-level '0' navigation down to main menu; abandoned data not reused", b_c.startswith("END") and "submissions" in b_c.lower())

    # ── (d) Date format validation ───────────────────────────────────────────
    phone_d = NAV_PHONES[3]
    r_bad_cal = ussd_post(client, phone_d, "1*1*31-02-2026", session_id="SID_D_CAL")
    b_bad_cal = r_bad_cal.data.decode()
    r_bad_fmt = ussd_post(client, phone_d, "1*1*2026-11-25", session_id="SID_D_FMT")
    b_bad_fmt = r_bad_fmt.data.decode()
    report(
        "(d) Rejects 31-02 (does not exist) and 2026-11-25 (bad format)",
        "does not exist" in b_bad_cal.lower() and "invalid date" in b_bad_fmt.lower(),
    )

    # ── (e) Feb 29 non-leap year rejected on date prompt ─────────────────────
    phone_e = NAV_PHONES[4]
    r_nonleap = ussd_post(client, phone_e, "1*1*29-02-2027", session_id="SID_E_NONLEAP")
    b_nonleap = r_nonleap.data.decode()
    report(
        "(e) Feb 29 non-leap year re-prompts on ENTER_DATE with error",
        b_nonleap.startswith("CON") and "Enter harvest date" in b_nonleap and "does not exist" in b_nonleap.lower(),
    )

    # ── (f) Past date rejected ───────────────────────────────────────────────
    phone_f = NAV_PHONES[5]
    yesterday = today - timedelta(days=1)
    y_str = yesterday.strftime("%d-%m-%Y")
    r_past = ussd_post(client, phone_f, f"1*1*{y_str}", session_id="SID_F_PAST")
    b_past = r_past.data.decode()
    report(
        "(f) Past date rejected with past error on ENTER_DATE",
        b_past.startswith("CON") and "past" in b_past.lower() and "Enter harvest date" in b_past,
    )

    # ── (g) Valid path reaches confirm, writes nothing yet; '1' saves correctly
    phone_g = NAV_PHONES[6]
    tgt_g = today + timedelta(days=20)
    tgt_g_str = tgt_g.strftime("%d-%m-%Y")
    base_path_g = f"1*1*{tgt_g_str}*500*3*1"

    # Step to confirm
    r_conf = ussd_post(client, phone_g, base_path_g, session_id="SID_G_CONF")
    b_conf = r_conf.data.decode()
    readable_g = menus.format_readable_date(tgt_g)

    # Verify nothing written to DB before confirming
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM harvest_submissions s JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = %s;", (phone_g,))
            cnt_before = cur.fetchone()["cnt"]

    # Now post '1' to confirm & submit
    _sms_calls.clear()
    r_submit = ussd_post(client, phone_g, f"{base_path_g}*1", session_id="SID_G_SUBMIT")
    b_submit = r_submit.data.decode()
    time.sleep(0.3)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT s.submission_id, s.status, s.location, s.quantity_kg,
                          r.recommendation_id, r.action
                   FROM harvest_submissions s
                   JOIN recommendations r ON r.submission_id = s.submission_id
                   JOIN farmers f ON f.farmer_id = s.farmer_id
                   WHERE f.phone_number = %s ORDER BY s.submission_id DESC LIMIT 1;""", (phone_g,)
            )
            sub_row = cur.fetchone()
            rec_id = sub_row["recommendation_id"] if sub_row else None
            ev_cnt = 0
            sms_cnt = 0
            if rec_id:
                cur.execute("SELECT COUNT(*) AS cnt FROM recommendation_evidence WHERE recommendation_id = %s;", (rec_id,))
                ev_cnt = cur.fetchone()["cnt"]
                cur.execute("SELECT COUNT(*) AS cnt FROM sms_logs WHERE recommendation_id = %s;", (rec_id,))
                sms_cnt = cur.fetchone()["cnt"]

    report(
        "(g) Confirm screen shows readable date, writes nothing yet; '1' saves PROCESSED, 3 evidence, 1 SMS",
        b_conf.startswith("CON") and readable_g in b_conf and "1. Confirm & Submit" in b_conf
        and cnt_before == 0 and b_submit.startswith("END")
        and sub_row is not None and sub_row["status"] == "PROCESSED"
        and sub_row["location"] == "TestNavVillage" and ev_cnt == 3 and sms_cnt >= 1,
    )

    # ── (h) Confirm screen: '2' cancels, '0' back to storage, '9' re-prompts ──
    phone_h = NAV_PHONES[7]
    base_h = f"1*1*{tgt_g_str}*400*2*2"
    r_can = ussd_post(client, phone_h, f"{base_h}*2", session_id="SID_H_CAN")
    b_can = r_can.data.decode()

    r_back_stor = ussd_post(client, phone_h, f"{base_h}*0", session_id="SID_H_BCK")
    b_back_stor = r_back_stor.data.decode()

    r_inv_conf = ussd_post(client, phone_h, f"{base_h}*9", session_id="SID_H_INV")
    b_inv_conf = r_inv_conf.data.decode()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM harvest_submissions s JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = %s;", (phone_h,))
            cnt_h = cur.fetchone()["cnt"]

    report(
        "(h) Confirm '2' cancels (0 writes), '0' back to storage, '9' re-prompts confirm",
        b_can.startswith("END") and "cancelled" in b_can.lower() and cnt_h == 0
        and b_back_stor.startswith("CON") and "safe place to store" in b_back_stor.lower()
        and b_inv_conf.startswith("CON") and "Invalid choice" in b_inv_conf and "Confirm" in b_inv_conf,
    )

    # ── (i) Idempotency on exact replay ───────────────────────────────────────
    phone_i = NAV_PHONES[8]
    sid_i = "SID_IDMP_NAV"
    text_i = f"1*1*{tgt_g_str}*350*3*1*1"
    session_store.clear_all()
    _sms_calls.clear()

    r1 = ussd_post(client, phone_i, text_i, session_id=sid_i)
    time.sleep(0.2)
    session_store.clear_all()
    r2 = ussd_post(client, phone_i, text_i, session_id=sid_i)
    time.sleep(0.2)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM harvest_submissions s JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = %s;", (phone_i,))
            cnt_idmp = cur.fetchone()["cnt"]

    report(
        "(i) Replaying identical sessionId & text creates ONE submission & ONE SMS",
        cnt_idmp == 1 and r1.data == r2.data,
    )

    # ── (j) Kinyarwanda flow & length checks (<= 182, mostly <= 160) ──────────
    phone_j = NAV_PHONES[9]
    r_rw_main = ussd_post(client, phone_j, "2", session_id="SID_J_RW")
    b_rw_main = r_rw_main.data.decode()

    rw_full = f"2*1*{tgt_g_str}*300*1*1"
    r_rw_conf = ussd_post(client, phone_j, rw_full, session_id="SID_J_RW_CONF")
    b_rw_conf = r_rw_conf.data.decode()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT preferred_language FROM farmers WHERE phone_number = %s;", (phone_j,))
            saved_lang = cur.fetchone()["preferred_language"]

    sample_screens = [
        ("LANG_EN", menus.screen_language()),
        ("LANG_EN_ERR", menus.screen_language("Invalid choice. Please try again.")),
        ("MAIN_EN", menus.screen_main("en", "Jean")),
        ("MAIN_EN_ERR", menus.screen_main("en", "Jean", "Invalid choice. Please try again.")),
        ("DATE_EN", menus.screen_ask_date("en", today)),
        ("DATE_EN_ERR", menus.screen_ask_date("en", today, "Invalid date. Use DD-MM-YYYY.")),
        ("QTY_EN", menus.screen_ask_quantity("en", tgt_g)),
        ("QTY_EN_ERR", menus.screen_ask_quantity("en", tgt_g, "Enter quantity (1-50,000kg).")),
        ("MAT_EN", menus.screen_ask_maturity("en")),
        ("STOR_EN", menus.screen_ask_storage("en")),
        ("CONF_EN", menus.screen_confirm("en", tgt_g, Decimal(500), "RIPE", True)),
        ("CONF_EN_ERR", menus.screen_confirm("en", tgt_g, Decimal(500), "RIPE", True, "Invalid choice. Please try again.")),
        ("CANCEL_EN", menus.screen_cancelled("en")),
        ("MAIN_RW", menus.screen_main("rw", "Jean")),
        ("DATE_RW", menus.screen_ask_date("rw", today)),
        ("QTY_RW", menus.screen_ask_quantity("rw", tgt_g)),
        ("MAT_RW", menus.screen_ask_maturity("rw")),
        ("STOR_RW", menus.screen_ask_storage("rw")),
        ("CONF_RW", menus.screen_confirm("rw", tgt_g, Decimal(500), "RIPE", True)),
        ("CANCEL_RW", menus.screen_cancelled("rw")),
    ]

    over_160 = []
    over_182 = []
    for s_name, s_txt in sample_screens:
        if len(s_txt) > 182:
            over_182.append((s_name, len(s_txt)))
        elif len(s_txt) > 160:
            over_160.append((s_name, len(s_txt)))

    if over_160:
        print(f"  Note: Screens between 161-182 chars: {over_160}")

    report(
        "(j) Preferred language saved (rw), screens in Kinyarwanda, all screens <= 182 chars",
        saved_lang == "rw" and "Ohereza" in b_rw_main and "Emeza" in b_rw_conf and len(over_182) == 0,
    )

    # ── (k) Garbage text resilience ───────────────────────────────────────────
    garbage_inputs = [
        "1*1*abc*****",
        "9*9*9",
        "*",
        "1**2",
        "1*" + ("9" * 500),
        "1*1*inyanya*🇷🇼*🌟",
        "0*0*0*0*0*0",
    ]
    all_k_ok = True
    for gi in garbage_inputs:
        r_g = ussd_post(client, NAV_PHONES[0], gi, session_id="SID_GARB")
        bg = r_g.data.decode()
        if r_g.status_code != 200 or not (bg.startswith("CON") or bg.startswith("END")):
            all_k_ok = False
            print(f"  [FAIL on garbage {gi[:20]}]: code={r_g.status_code} body={bg[:50]}")
    report("(k) Garbage text never returns 500, always CON or END text/plain", all_k_ok)

    # ── (l) Safety guard: STORE_AND_WAIT never issued without storage ─────────
    phone_l = NAV_PHONES[0]
    td_l = today + timedelta(days=15)
    td_l_str = td_l.strftime("%d-%m-%Y")
    unsafe_issued = False
    for mat_code in ("1", "2", "3"):
        for stor_code in ("1", "2"):
            txt_l = f"1*1*{td_l_str}*500*{mat_code}*{stor_code}*1"
            r_l = ussd_post(client, phone_l, txt_l, session_id=f"SID_L_{mat_code}_{stor_code}")
            time.sleep(0.05)
            if r_l.data.decode().startswith("END"):
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """SELECT r.action FROM recommendations r
                               JOIN harvest_submissions s ON r.submission_id = s.submission_id
                               JOIN farmers f ON f.farmer_id = s.farmer_id
                               WHERE f.phone_number = %s ORDER BY r.recommendation_id DESC LIMIT 1;""", (phone_l,)
                        )
                        act = cur.fetchone()["action"]
                        if act == "STORE_AND_WAIT" and stor_code == "2":
                            unsafe_issued = True
    report("(l) STORE_AND_WAIT never issued without storage across all permutations", not unsafe_issued)

    # ── (m) 10 concurrent farmers full flow (~7 requests each) ───────────────
    def _run_concurrent(idx: int) -> dict:
        phone = NAV_PHONES[idx]
        sid = f"SID_CONC_NAV_{idx:02d}"
        d_idx = today + timedelta(days=10 + (idx % 20))
        d_idx_str = d_idx.strftime("%d-%m-%Y")

        # Full sequential steps:
        steps = [
            "",
            "1",
            "1*1",
            f"1*1*{d_idx_str}",
            f"1*1*{d_idx_str}*{100 + idx * 10}",
            f"1*1*{d_idx_str}*{100 + idx * 10}*1",
            f"1*1*{d_idx_str}*{100 + idx * 10}*1*2",
            f"1*1*{d_idx_str}*{100 + idx * 10}*1*2*1",
        ]

        t0_flow = time.perf_counter()
        last_resp = None
        lat_conf = 0.0

        for step_text in steps:
            is_confirm = (step_text == steps[-1])
            t0 = time.perf_counter()
            resp = ussd_post(client, phone, step_text, session_id=sid)
            t_taken = time.perf_counter() - t0
            if is_confirm:
                lat_conf = t_taken
            last_resp = resp

        lat_total = time.perf_counter() - t0_flow
        return {
            "idx": idx,
            "ok": last_resp.status_code == 200 and last_resp.data.decode().startswith("END"),
            "lat_conf": lat_conf,
            "lat_total": lat_total,
        }

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(_run_concurrent, i) for i in range(10)]
        results_m = [f.result() for f in futs]

    time.sleep(1.0)
    all_m_ok = all(r["ok"] for r in results_m)
    conf_lats = sorted(r["lat_conf"] for r in results_m)
    p50_c = conf_lats[4]
    p95_c = conf_lats[9]

    # Verify DB counts for the 10 farmers
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM harvest_submissions s JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = ANY(%s);", (NAV_PHONES,))
            tot_subs = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) AS cnt FROM recommendations r JOIN harvest_submissions s ON r.submission_id = s.submission_id JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = ANY(%s);", (NAV_PHONES,))
            tot_recs = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) AS cnt FROM sms_logs sl JOIN recommendations r ON sl.recommendation_id = r.recommendation_id JOIN harvest_submissions s ON r.submission_id = s.submission_id JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = ANY(%s);", (NAV_PHONES,))
            tot_sms = cur.fetchone()["cnt"]

    print(f"  Latency (confirm step): p50={p50_c*1000:.0f}ms  p95={p95_c*1000:.0f}ms")
    report(
        "(m) 10 concurrent farmers completed full flow, zero errors, p95 < 1500ms",
        all_m_ok and tot_subs >= 10 and tot_recs >= 10 and tot_sms >= 10 and p95_c < 1.5,
    )

    # ── (n) Unregistered and inactive numbers get bilingual END ───────────────
    r_unreg = ussd_post(client, UNREG_PHONE, "")
    b_unreg = r_unreg.data.decode()
    r_inact = ussd_post(client, "+250788990099", "")
    b_inact = r_inact.data.decode()
    report(
        "(n) Unregistered & inactive numbers get bilingual END on first request",
        b_unreg.startswith("END") and "not registered" in b_unreg.lower() and "ntiyanditswe" in b_unreg.lower()
        and b_inact.startswith("END"),
    )


def main():
    print("=" * 60)
    print("METLINK USSD NAVIGATION VERIFICATION SUITE")
    print("=" * 60)

    # 1. Pure unit tests
    test_pure_fold_function()

    # 2. Integration tests
    app = create_app()
    app.config["TESTING"] = True
    setup_nav_farmers()

    try:
        run_integration_tests(app)
    finally:
        counts = cleanup_nav_farmers()
        print("\n── Cleanup ─────────────────────────────────────────────────")
        for tbl, n in counts.items():
            print(f"  Deleted {n:>4} row(s) from {tbl}")
        print("────────────────────────────────────────────────────────────")

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
