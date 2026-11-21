"""
METLINK USSD & SMS Fixes Verification Suite.

Validates:
(1) Single-step date entry in USSD (ENTER_DATE).
(2) Every SMS produces a complete sms_logs row and shows on admin Logs.
(3) Africa's Talking simulator never hangs (never-hang guards, lock timeout, 404/405 wrappers).

Checks (a) through (l).
"""

from __future__ import annotations

import itertools
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app import create_app
from backend.services import engine, menus, session_store
import backend.services.sms_service as sms_svc
from database.connector import get_connection, get_cursor

FIX_PHONES = [f"+25078899002{i}" for i in range(1, 10)] + ["+250788990030"]

passed = 0
failed = 0
_mock_id_gen = itertools.count(1)


def report(label: str, ok: bool, detail: str = ""):
    global passed, failed
    if ok:
        passed += 1
        print(f"[PASS] {label}")
    else:
        failed += 1
        print(f"[FAIL] {label} — {detail}")


def setup_fix_farmers():
    """Insert test farmers (FIX_PHONES)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            for i, phone in enumerate(FIX_PHONES, start=1):
                cur.execute(
                    """
                    INSERT INTO farmers
                        (phone_number, name, location, preferred_language,
                         registration_source, registered_by, is_active)
                    VALUES (%s, %s, 'TestFixVillage', 'en', 'admin', 1, TRUE)
                    ON CONFLICT (phone_number) DO UPDATE SET is_active = TRUE, preferred_language = 'en';
                    """,
                    (phone, f"TEST_FixFarmer_{i:02d}"),
                )


def cleanup_fix_farmers():
    """Delete ONLY rows tied to FIX_PHONES in foreign key order."""
    counts = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT farmer_id FROM farmers WHERE phone_number = ANY(%s);", (FIX_PHONES,))
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


def ussd_post(client, phone, text, session_id=None, token_param=None):
    if session_id is None:
        session_id = f"SID_FIX_{phone}"
    if token_param is None:
        token_param = os.getenv("AT_WEBHOOK_TOKEN", "").strip("\"'")
    url = "/api/ussd/callback"
    if token_param:
        url += f"?token={token_param}"
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


_sms_calls: List[Dict[str, Any]] = []


def _mock_provider(phone_number: str, message: str) -> Dict[str, Any]:
    global _sms_calls
    call_info = {
        "phone_number": phone_number,
        "message": message,
        "provider_id": f"ATXid_mock_{next(_mock_id_gen):06d}",
        "status": "Success",
        "statusCode": 101,
    }
    _sms_calls.append(call_info)
    return call_info


# ============================================================================
# Main Checks
# ============================================================================

def run_tests():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    setup_fix_farmers()
    today = menus.get_today_kigali()

    try:
        sms_svc.set_sms_provider(_mock_provider)

        # ── Check (a): Pure tests of parse_harvest_date ──────────────────────
        print("\n--- Check (a): Pure tests of parse_harvest_date ---")
        t_ref = date(2026, 11, 22)
        # Accepted formats
        accepted = [
            ("25-11-2026", date(2026, 11, 25)),
            ("25 11 2026", date(2026, 11, 25)),
            ("25/11/2026", date(2026, 11, 25)),
            ("25.11.2026", date(2026, 11, 25)),
            ("25112026", date(2026, 11, 25)),
            ("5-1-2027", date(2027, 1, 5)),
            (t_ref.strftime("%d-%m-%Y"), t_ref),  # today is accepted
        ]
        all_acc_ok = True
        for raw, exp in accepted:
            p_d, err = menus.parse_harvest_date(raw, today=t_ref)
            if p_d != exp or err is not None:
                all_acc_ok = False
                print(f"  [FAIL accepted on {raw}]: got ({p_d}, {err}) expected {exp}")
        report("(a) Accepted formats parsed accurately (DD-MM-YYYY, DDMMYYYY, slashes, dots, spaces)", all_acc_ok)

        # Rejected formats -> BAD_FORMAT
        rejected = ["5112026", "2026-11-25", "25-11-26", "25.5-11-2026", "abc", "25-Nov-2026", ""]
        all_rej_ok = True
        for raw in rejected:
            p_d, err = menus.parse_harvest_date(raw, today=t_ref)
            if p_d is not None or err != "BAD_FORMAT":
                all_rej_ok = False
                print(f"  [FAIL rejected on {raw}]: got ({p_d}, {err})")
        report("(a) Rejected formats return BAD_FORMAT (7-digits, YYYY-MM-DD, 2-digit yr, letters)", all_rej_ok)

        # Calendar existence
        p_d_cal, err_cal = menus.parse_harvest_date("31-02-2026", today=t_ref)
        p_d_nonleap, err_nonleap = menus.parse_harvest_date("29-02-2027", today=t_ref)
        p_d_leap, err_leap = menus.parse_harvest_date("29-02-2028", today=date(2028, 1, 1))
        report(
            "(a) 31-02-2026 and 29-02-2027 return BAD_CALENDAR; 29-02-2028 (leap year) accepted",
            err_cal == "BAD_CALENDAR" and err_nonleap == "BAD_CALENDAR" and p_d_leap == date(2028, 2, 29),
        )

        # Past date
        yesterday = t_ref - timedelta(days=1)
        p_d_past, err_past = menus.parse_harvest_date(yesterday.strftime("%d-%m-%Y"), today=t_ref)
        report("(a) Yesterday returns PAST", err_past == "PAST" and p_d_past is None)

        # Beyond limit
        far_future = t_ref + timedelta(days=engine.MAX_DAYS_AHEAD + 1)
        p_d_far, err_far = menus.parse_harvest_date(far_future.strftime("%d-%m-%Y"), today=t_ref)
        report("(a) Date beyond MAX_DAYS_AHEAD returns TOO_FAR", err_far == "TOO_FAR" and p_d_far is None)

        # ── Check (b): Cumulative text via endpoint ──────────────────────────
        print("\n--- Check (b): Single-step date prompt via endpoint ---")
        phone_b = FIX_PHONES[0]
        # 1. Date prompt shows future example date
        r_dt_screen = ussd_post(client, phone_b, "1*1", session_id="SID_B_PROMPT")
        b_dt_screen = r_dt_screen.data.decode()
        ex_d = (today + timedelta(days=30)).strftime("%d-%m-%Y")
        report(
            "(b) Date prompt shows future example date (today + 30 days)",
            b_dt_screen.startswith("CON") and ex_d in b_dt_screen and "Enter harvest date" in b_dt_screen,
        )

        # 2. Yesterday rejected on same screen with past error, nothing saved
        r_past = ussd_post(client, phone_b, f"1*1*{(today - timedelta(days=1)).strftime('%d-%m-%Y')}", session_id="SID_B_PAST")
        b_past = r_past.data.decode()
        report(
            "(b) Yesterday rejected on same screen with past error",
            b_past.startswith("CON") and "past" in b_past.lower() and "Enter harvest date" in b_past,
        )

        # 3. Valid date as DD-MM-YYYY and DDMMYYYY both continue, quantity starts with "Date: D Mon YYYY"
        v_d = today + timedelta(days=20)
        v_d_dash = v_d.strftime("%d-%m-%Y")
        v_d_compact = v_d.strftime("%d%m%Y")
        read_d = menus.format_readable_date(v_d)

        r_dash = ussd_post(client, phone_b, f"1*1*{v_d_dash}", session_id="SID_B_DASH")
        b_dash = r_dash.data.decode()
        r_comp = ussd_post(client, phone_b, f"1*1*{v_d_compact}", session_id="SID_B_COMP")
        b_comp = r_comp.data.decode()

        report(
            "(b) DD-MM-YYYY and DDMMYYYY both advance to quantity with 'Date: D Mon YYYY'",
            b_dash.startswith("CON") and f"Date: {read_d}" in b_dash and "Quantity" in b_dash
            and b_comp.startswith("CON") and f"Date: {read_d}" in b_comp and "Quantity" in b_comp,
        )

        # 4. "0" at date step returns to main menu
        r_b_back = ussd_post(client, phone_b, "1*1*0", session_id="SID_B_BACK")
        b_b_back = r_b_back.data.decode()
        report("(b) '0' at date step returns to main menu", b_b_back.startswith("CON") and "Submit expected harvest" in b_b_back)

        # 5. Bad token then valid token moves on (no stuck state)
        r_bad_then_good = ussd_post(client, phone_b, f"1*1*invalid*{v_d_dash}", session_id="SID_B_RESILIENT")
        b_bad_then_good = r_bad_then_good.data.decode()
        report("(b) Bad token then valid token moves on without stuck state", b_bad_then_good.startswith("CON") and f"Date: {read_d}" in b_bad_then_good)

        # ── Check (c): Confirm screen and submission ─────────────────────────
        print("\n--- Check (c): Confirm screen & Kinyarwanda ---")
        phone_c = FIX_PHONES[1]
        v_d_c = today + timedelta(days=20)
        v_d_c_str = v_d_c.strftime("%d-%m-%Y")
        read_c = menus.format_readable_date(v_d_c)

        # Reach confirm in English
        conf_path = f"1*1*{v_d_c_str}*500*3*1"
        r_conf_c = ussd_post(client, phone_c, conf_path, session_id="SID_C_CONF")
        b_conf_c = r_conf_c.data.decode()

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM harvest_submissions s JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = %s;", (phone_c,))
                cnt_c_zero = cur.fetchone()["cnt"]

        # Confirm choice 1 saves
        _sms_calls.clear()
        r_sub_c = ussd_post(client, phone_c, f"{conf_path}*1", session_id="SID_C_CONF")
        b_sub_c = r_sub_c.data.decode()
        time.sleep(0.3)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT s.status, r.recommendation_id FROM harvest_submissions s
                       JOIN recommendations r ON r.submission_id = s.submission_id
                       JOIN farmers f ON f.farmer_id = s.farmer_id
                       WHERE f.phone_number = %s;""", (phone_c,)
                )
                row_c = cur.fetchone()
                ev_c_cnt = 0
                sms_c_cnt = 0
                if row_c:
                    cur.execute("SELECT COUNT(*) AS cnt FROM recommendation_evidence WHERE recommendation_id = %s;", (row_c["recommendation_id"],))
                    ev_c_cnt = cur.fetchone()["cnt"]
                    cur.execute("SELECT COUNT(*) AS cnt FROM sms_logs WHERE recommendation_id = %s;", (row_c["recommendation_id"],))
                    sms_c_cnt = cur.fetchone()["cnt"]

        report(
            "(c) Confirm shows readable date, writes nothing yet; '1' saves PROCESSED, 3 evidence, 1 SMS",
            b_conf_c.startswith("CON") and read_c in b_conf_c and "Qty: 500kg" in b_conf_c
            and cnt_c_zero == 0 and b_sub_c.startswith("END")
            and row_c is not None and row_c["status"] == "PROCESSED"
            and ev_c_cnt == 3 and sms_c_cnt == 1,
        )

        # Confirm choices 2 (cancel), 0 (back), 9 (re-prompt)
        phone_c2 = FIX_PHONES[2]
        base_c2 = f"1*1*{v_d_c_str}*400*2*2"
        b_can = ussd_post(client, phone_c2, f"{base_c2}*2", session_id="SID_C2_CAN").data.decode()
        b_bck = ussd_post(client, phone_c2, f"{base_c2}*0", session_id="SID_C2_BCK").data.decode()
        b_inv = ussd_post(client, phone_c2, f"{base_c2}*9", session_id="SID_C2_INV").data.decode()
        report(
            "(c) Confirm choices: '2' cancels, '0' back to storage, '9' re-prompts",
            b_can.startswith("END") and "cancelled" in b_can.lower()
            and b_bck.startswith("CON") and ("store" in b_bck.lower() or "kubika" in b_bck.lower())
            and b_inv.startswith("CON") and "Invalid choice" in b_inv,
        )

        # Kinyarwanda flow
        phone_rw = FIX_PHONES[3]
        b_rw_conf = ussd_post(client, phone_rw, f"2*1*{v_d_c_str}*350*1*1", session_id="SID_RW_CONF").data.decode()
        report("(c) Kinyarwanda confirm screen in rw", "Emeza umusaruro" in b_rw_conf and "Itariki:" in b_rw_conf and "Ibiro: 350kg" in b_rw_conf)

        # ── Check (d): Mock SMS success ──────────────────────────────────────
        print("\n--- Check (d): SMS logging on mock success ---")
        phone_d = FIX_PHONES[4]
        _sms_calls.clear()
        v_d_d = today + timedelta(days=22)
        r_d = ussd_post(client, phone_d, f"1*1*{v_d_d.strftime('%d-%m-%Y')}*600*3*1*1", session_id="SID_D_SMS")
        time.sleep(0.3)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT sl.*, r.recommendation_id FROM sms_logs sl
                       JOIN recommendations r ON sl.recommendation_id = r.recommendation_id
                       JOIN harvest_submissions s ON r.submission_id = s.submission_id
                       JOIN farmers f ON f.farmer_id = s.farmer_id
                       WHERE f.phone_number = %s;""", (phone_d,)
                )
                sms_row_d = cur.fetchone()

        report(
            "(d) Mock success: status SENT, provider_id ATXid_..., sent_at set, delivered_at NULL",
            sms_row_d is not None and sms_row_d["status"] == "SENT"
            and str(sms_row_d["provider_id"]).startswith("ATXid_")
            and sms_row_d["sent_at"] is not None and sms_row_d["delivered_at"] is None,
        )

        # ── Check (e): SMS failure paths ─────────────────────────────────────
        print("\n--- Check (e): SMS logging on failure paths ---")
        # 1. Mock recipient failure (e.g. InvalidSenderId / status FAILED)
        def _failing_recipient(p, m):
            return {
                "SMSMessageData": {
                    "Recipients": [{"messageId": "ATXid_err_001", "status": "InvalidSenderId", "statusCode": 400}]
                }
            }
        sms_svc.set_sms_provider(_failing_recipient)
        res_fail = sms_svc.send_sms_sync(sms_row_d["recommendation_id"], phone_d, "Test fail msg")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, provider_id FROM sms_logs WHERE message = 'Test fail msg';")
                r_log_f = cur.fetchone()
        report("(e) Mock recipient failure creates row FAILED with provider_id NULL", res_fail["status"] == "FAILED" and r_log_f["status"] == "FAILED" and r_log_f["provider_id"] is None)

        # 2. Mock provider exception
        def _exploding_provider(p, m):
            raise ConnectionError("Mock carrier outage")
        sms_svc.set_sms_provider(_exploding_provider)
        res_exc = sms_svc.send_sms_sync(sms_row_d["recommendation_id"], phone_d, "Test exc msg")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, provider_id FROM sms_logs WHERE message = 'Test exc msg';")
                r_log_exc = cur.fetchone()
        report("(e) Mock exception creates row FAILED without raising", res_exc["status"] == "FAILED" and r_log_exc["status"] == "FAILED")

        # 3. Missing API key in live mode
        orig_key = os.environ.get("AT_API_KEY")
        try:
            os.environ["SMS_MODE"] = "live"
            os.environ["AT_API_KEY"] = ""
            res_nokey = sms_svc.send_sms_sync(sms_row_d["recommendation_id"], phone_d, "Test nokey msg")
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT status FROM sms_logs WHERE message = 'Test nokey msg';")
                    r_log_nokey = cur.fetchone()
            report("(e) Missing API key in live mode logs FAILED row", res_nokey["status"] == "FAILED" and r_log_nokey["status"] == "FAILED")
        finally:
            if orig_key is not None:
                os.environ["AT_API_KEY"] = orig_key
            os.environ.pop("SMS_MODE", None)

        # 4. Break first DB insert on purpose: retry still creates one row
        attempts = [0]
        orig_get_cursor = sms_svc.get_cursor

        from contextlib import contextmanager
        @contextmanager
        def flaky_get_cursor():
            attempts[0] += 1
            if attempts[0] == 1:
                raise RuntimeError("Simulated transient DB insert connection glitch")
            with orig_get_cursor() as cur:
                yield cur

        sms_svc.get_cursor = flaky_get_cursor
        sms_svc.set_sms_provider(_mock_provider)
        try:
            res_retry = sms_svc.send_sms_sync(sms_row_d["recommendation_id"], phone_d, "Test retry msg")
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT status FROM sms_logs WHERE message = 'Test retry msg';")
                    r_retry_log = cur.fetchone()
            report("(e) First DB insert failure retries on fresh cursor and creates row", r_retry_log is not None and attempts[0] == 2)
        finally:
            sms_svc.get_cursor = orig_get_cursor

        # ── Check (f): SMS_SANDBOX_AUTO_DELIVERED ────────────────────────────
        print("\n--- Check (f): SMS_SANDBOX_AUTO_DELIVERED flag ---")
        phone_f = FIX_PHONES[5]
        orig_auto = os.environ.get("SMS_SANDBOX_AUTO_DELIVERED")
        orig_user = os.environ.get("AT_USERNAME")
        try:
            # 1. auto=true, username=sandbox -> DELIVERED
            os.environ["SMS_SANDBOX_AUTO_DELIVERED"] = "true"
            os.environ["AT_USERNAME"] = "sandbox"
            os.environ["SMS_MODE"] = "live"
            res_sbx_deliv = sms_svc.send_sms_sync(sms_row_d["recommendation_id"], phone_f, "Test sbx auto deliv")
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT status, delivered_at FROM sms_logs WHERE message = 'Test sbx auto deliv';")
                    r_sbx_deliv = cur.fetchone()
            report(
                "(f) auto_delivered=true with sandbox sets DELIVERED and delivered_at",
                r_sbx_deliv["status"] == "DELIVERED" and r_sbx_deliv["delivered_at"] is not None,
            )

            # 2. auto=false -> SENT
            os.environ["SMS_SANDBOX_AUTO_DELIVERED"] = "false"
            res_sbx_sent = sms_svc.send_sms_sync(sms_row_d["recommendation_id"], phone_f, "Test sbx sent")
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT status, delivered_at FROM sms_logs WHERE message = 'Test sbx sent';")
                    r_sbx_sent = cur.fetchone()
            report("(f) auto_delivered=false sets SENT with delivered_at NULL", r_sbx_sent["status"] == "SENT" and r_sbx_sent["delivered_at"] is None)

            # 3. auto=true but different username -> SENT
            os.environ["SMS_SANDBOX_AUTO_DELIVERED"] = "true"
            os.environ["AT_USERNAME"] = "production_user"
            res_prod = sms_svc.send_sms_sync(sms_row_d["recommendation_id"], phone_f, "Test prod auto deliv")
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT status, delivered_at FROM sms_logs WHERE message = 'Test prod auto deliv';")
                    r_prod = cur.fetchone()
            report("(f) auto_delivered=true with non-sandbox user remains SENT", r_prod["status"] == "SENT" and r_prod["delivered_at"] is None)
        finally:
            if orig_auto is not None:
                os.environ["SMS_SANDBOX_AUTO_DELIVERED"] = orig_auto
            else:
                os.environ.pop("SMS_SANDBOX_AUTO_DELIVERED", None)
            if orig_user is not None:
                os.environ["AT_USERNAME"] = orig_user
            else:
                os.environ.pop("AT_USERNAME", None)
            os.environ.pop("SMS_MODE", None)

        # ── Check (g): Delivery webhook race guard & security ────────────────
        print("\n--- Check (g): Delivery webhook & race guard ---")
        token_secret = os.getenv("AT_WEBHOOK_TOKEN", "").strip("\"'")
        p_id = "ATXid_webhook_test_001"
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO sms_logs (recommendation_id, phone_number, message, status, provider_id, sent_at) VALUES (%s, %s, 'wh test', 'SENT', %s, CURRENT_TIMESTAMP);",
                (sms_row_d["recommendation_id"], phone_d, p_id),
            )

        # Form post transitions to DELIVERED
        r_wh_form = client.post(f"/api/webhooks/sms-delivery?token={token_secret}", data={"id": p_id, "status": "Success"})
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, delivered_at FROM sms_logs WHERE provider_id = %s;", (p_id,))
                r_wh_chk = cur.fetchone()
        report("(g) Form POST transitions SENT to DELIVERED with delivered_at", r_wh_form.status_code == 200 and r_wh_chk["status"] == "DELIVERED" and r_wh_chk["delivered_at"] is not None)

        # Never downgrade DELIVERED
        client.post(f"/api/webhooks/sms-delivery?token={token_secret}", data={"id": p_id, "status": "Failed"})
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM sms_logs WHERE provider_id = %s;", (p_id,))
                r_no_down = cur.fetchone()
        report("(g) Never downgrades DELIVERED row", r_no_down["status"] == "DELIVERED")

        # Race guard: webhook arriving 0.5s before row exists
        race_id = "ATXid_race_test_999"
        def _delayed_insert():
            time.sleep(0.4)
            with get_cursor() as cur:
                cur.execute(
                    "INSERT INTO sms_logs (recommendation_id, phone_number, message, status, provider_id, sent_at) VALUES (%s, %s, 'wh race', 'SENT', %s, CURRENT_TIMESTAMP);",
                    (sms_row_d["recommendation_id"], phone_d, race_id),
                )
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_ins = ex.submit(_delayed_insert)
            # Webhook fires concurrently
            r_race = client.post(f"/api/webhooks/sms-delivery?token={token_secret}", json={"id": race_id, "status": "Success"})
            f_ins.result()

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM sms_logs WHERE provider_id = %s;", (race_id,))
                r_race_chk = cur.fetchone()
        report("(g) Report arriving before row exists updates via race guard", r_race.status_code == 200 and r_race_chk is not None and r_race_chk["status"] == "DELIVERED")

        # Unknown id returns 200; wrong token returns 403
        r_unk = client.post(f"/api/webhooks/sms-delivery?token={token_secret}", json={"id": "unknown_id_xyz", "status": "Success"})
        r_wrong_tok = client.post("/api/webhooks/sms-delivery?token=wrong_token", json={"id": p_id, "status": "Success"})
        report("(g) Unknown id returns 200; wrong token returns 403", r_unk.status_code == 200 and r_wrong_tok.status_code == 403)

        # ── Check (h): Admin API GET /api/sms-logs ───────────────────────────
        print("\n--- Check (h): Admin API GET /api/sms-logs ---")
        # Login admin aline.uwase to get JWT
        login_res = client.post("/api/auth/login", json={"username": "aline.uwase", "password": "Admin@1234"})
        admin_token = login_res.get_json().get("token")
        r_sms_logs = client.get("/api/sms-logs", headers={"Authorization": f"Bearer {admin_token}"})
        logs_data = r_sms_logs.get_json().get("sms_logs", [])
        has_req_cols = False
        if logs_data:
            item0 = logs_data[0]
            has_req_cols = ("provider_id" in item0 and "status" in item0 and "sent_at" in item0 and "delivered_at" in item0)
        report("(h) GET /api/sms-logs returns provider_id, status, sent_at and delivered_at", r_sms_logs.status_code == 200 and has_req_cols)

        # ── Check (i): Never-hang error resilience ───────────────────────────
        print("\n--- Check (i): Never-hang crash resilience & timeout ---")
        # Monkeypatch menus.handle to raise
        orig_handle = menus.handle
        menus.handle = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Monkeypatched menu crash"))
        try:
            r_crash = ussd_post(client, phone_b, "1*1")
            b_crash = r_crash.data.decode()
            report(
                "(i) Handled exception in menu logic returns 200 text/plain starting with END",
                r_crash.status_code == 200 and r_crash.content_type.startswith("text/plain") and b_crash.startswith("END"),
            )
        finally:
            menus.handle = orig_handle

        # Monkeypatch slow lock to test timeout
        orig_acq = session_store.acquire_session_lock
        session_store.acquire_session_lock = lambda sid, timeout=5.0: False
        try:
            r_lock_to = ussd_post(client, phone_b, "1*1")
            b_lock_to = r_lock_to.data.decode()
            report("(i) Slow lock acquisition timeout returns 200 END error", r_lock_to.status_code == 200 and b_lock_to.startswith("END"))
        finally:
            session_store.acquire_session_lock = orig_acq

        # ── Check (j): 404 / 405 error handlers & garbage text ────────────────
        print("\n--- Check (j): 404/405 under /api/ussd & garbage text ---")
        r_405 = client.get(f"/api/ussd/callback?token={token_secret}")
        b_405 = r_405.data.decode()
        r_404 = client.post(f"/api/ussd/nonexistent?token={token_secret}")
        b_404 = r_404.data.decode()
        report(
            "(j) 404 and 405 under /api/ussd return 200 text/plain starting with END",
            r_405.status_code == 200 and b_405.startswith("END") and r_405.content_type.startswith("text/plain")
            and r_404.status_code == 200 and b_404.startswith("END"),
        )

        garbage_list = ["1**2", "*", "a" * 500, "1*🇷🇼*🌟", "0*0*0*0*0*0"]
        all_garb_ok = True
        for g in garbage_list:
            rg = ussd_post(client, phone_b, g)
            bg = rg.data.decode()
            if rg.status_code != 200 or not (bg.startswith("CON") or bg.startswith("END")):
                all_garb_ok = False
        report("(j) Garbage text values always return 200 with CON or END", all_garb_ok)

        # ── Check (k): Latencies & 10 concurrent farmers ──────────────────────
        print("\n--- Check (k): Latencies & 10 concurrent farmers ---")
        # Non-confirm latency over 50 calls
        non_conf_lats = []
        for i in range(50):
            t0 = time.perf_counter()
            ussd_post(client, FIX_PHONES[i % 5], "1*1")
            non_conf_lats.append(time.perf_counter() - t0)
        non_conf_lats.sort()
        p50_nc = non_conf_lats[24]
        p95_nc = non_conf_lats[47]
        print(f"  Non-confirm latency (50 calls): p50={p50_nc*1000:.1f}ms  p95={p95_nc*1000:.1f}ms")
        report("(k) Non-confirm screens answer in under 300 ms (p95)", p95_nc < 0.3)

        # 10 concurrent farmers
        def _run_conc(idx: int):
            ph = FIX_PHONES[idx]
            sid = f"SID_CONC_FIX_{idx:02d}"
            d_tgt = (today + timedelta(days=10 + idx)).strftime("%d-%m-%Y")
            steps = ["", "1", "1*1", f"1*1*{d_tgt}", f"1*1*{d_tgt}*400", f"1*1*{d_tgt}*400*2", f"1*1*{d_tgt}*400*2*1", f"1*1*{d_tgt}*400*2*1*1"]
            lat_conf = 0.0
            last_resp = None
            for s in steps:
                is_c = (s == steps[-1])
                t0 = time.perf_counter()
                r = ussd_post(client, ph, s, session_id=sid)
                taken = time.perf_counter() - t0
                if is_c:
                    lat_conf = taken
                last_resp = r
            return {
                "ok": last_resp.status_code == 200 and last_resp.data.decode().startswith("END"),
                "lat_conf": lat_conf,
            }

        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = [ex.submit(_run_conc, i) for i in range(10)]
            c_res = [f.result() for f in futs]
        time.sleep(1.0)

        all_c_ok = all(r["ok"] for r in c_res)
        conf_lats_k = sorted(r["lat_conf"] for r in c_res)
        p95_ck = conf_lats_k[9]
        print(f"  Confirm step latency (10 concurrent): p95={p95_ck*1000:.1f}ms")

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS cnt FROM harvest_submissions s JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = ANY(%s);", (FIX_PHONES,))
                tot_subs = cur.fetchone()["cnt"]
                cur.execute("SELECT COUNT(*) AS cnt FROM recommendations r JOIN harvest_submissions s ON r.submission_id = s.submission_id JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = ANY(%s);", (FIX_PHONES,))
                tot_recs = cur.fetchone()["cnt"]
                cur.execute("SELECT COUNT(*) AS cnt FROM sms_logs sl JOIN recommendations r ON sl.recommendation_id = r.recommendation_id JOIN harvest_submissions s ON r.submission_id = s.submission_id JOIN farmers f ON s.farmer_id = f.farmer_id WHERE f.phone_number = ANY(%s);", (FIX_PHONES,))
                tot_sms = cur.fetchone()["cnt"]

        report(
            "(k) 10 concurrent farmers run full flow with zero errors, p95 < 1.5s, submissions/recs/sms created",
            all_c_ok and tot_subs >= 10 and tot_recs >= 10 and tot_sms >= 10 and p95_ck < 1.5,
        )

    finally:
        sms_svc.reset_sms_provider()
        counts = cleanup_fix_farmers()
        print("\n── Cleanup ─────────────────────────────────────────────────")
        for tbl, n in counts.items():
            print(f"  Deleted {n:>4} row(s) from {tbl}")
        print("────────────────────────────────────────────────────────────")


def main():
    print("=" * 60)
    print("METLINK USSD & SMS FIXES VERIFICATION SUITE")
    print("=" * 60)

    run_tests()

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
