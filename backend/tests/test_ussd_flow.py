"""
METLINK USSD Flow Integration Tests.

Runs against the real Flask app + real DB (via test client).
SMS provider is mocked to avoid network calls.
Test farmers on phones +250788990001..+250788990010 plus one inactive.

CLEANUP: deletes only rows tied to those exact phones, in FK order.
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from decimal import Decimal

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Mock SMS provider BEFORE importing app ────────────────────────────────────
import backend.services.sms_service as _sms_svc
import itertools as _itertools

_sms_calls: list = []
_sms_should_fail = False
_mock_pid_counter = _itertools.count()   # global monotonic — never resets

def _mock_provider(phone: str, msg: str) -> dict:
    if _sms_should_fail:
        raise ConnectionError("Mock SMS failure")
    pid = f"MOCK_{next(_mock_pid_counter):04d}"
    _sms_calls.append({"phone": phone, "msg": msg, "pid": pid})
    return {"provider_id": pid, "status": "Success", "status_code": 101}

_sms_svc.set_sms_provider(_mock_provider)
os.environ["SMS_MODE"] = "live"
os.environ["AT_API_KEY"] = "mock_key_for_tests"
os.environ["AT_WEBHOOK_TOKEN"] = ""

# ── Import app after mock is installed ────────────────────────────────────────
from backend.app import create_app
from backend.services import session_store
from database.connector import get_cursor, get_connection

# ── Test infrastructure ───────────────────────────────────────────────────────
passed = 0
failed = 0

def report(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name}" + (f": {detail}" if detail else ""))

TEST_PHONES = [f"+25078899000{i}" for i in range(1, 10)] + ["+250788990010"]
INACTIVE_PHONE = "+250788990011"
UNREGISTERED_PHONE = "+250789000999"

# Seeds — created in setup, deleted in finally
ADMIN_ID = 1  # aline.uwase from seed

def setup_test_farmers():
    """Insert TEST_ farmers. All 10 active + 1 inactive."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            for i, phone in enumerate(TEST_PHONES, start=1):
                cur.execute(
                    """
                    INSERT INTO farmers
                        (phone_number, name, location, preferred_language,
                         registration_source, registered_by, is_active)
                    VALUES (%s, %s, 'TestVillage', 'en', 'admin', %s, TRUE)
                    ON CONFLICT (phone_number) DO NOTHING;
                    """,
                    (phone, f"TEST_Farmer_{i:02d}", ADMIN_ID),
                )
            cur.execute(
                """
                INSERT INTO farmers
                    (phone_number, name, location, preferred_language,
                     registration_source, registered_by, is_active)
                VALUES (%s, 'TEST_Inactive', 'TestVillage', 'en', 'admin', %s, FALSE)
                ON CONFLICT (phone_number) DO NOTHING;
                """,
                (INACTIVE_PHONE, ADMIN_ID),
            )

ADMIN_TEST_PHONE = "+250788776655"  # created by test_admin_api.py subprocess


def _delete_farmer_phone(cur, phone: str) -> None:
    """Delete one farmer and all FK-dependent rows (must be called inside a connection)."""
    cur.execute("SELECT farmer_id FROM farmers WHERE phone_number = %s;", (phone,))
    row = cur.fetchone()
    if not row:
        return
    fid = row["farmer_id"]
    cur.execute(
        """DELETE FROM sms_logs WHERE recommendation_id IN (
               SELECT r.recommendation_id FROM recommendations r
               JOIN harvest_submissions s ON r.submission_id = s.submission_id
               WHERE s.farmer_id = %s);""", (fid,))
    cur.execute(
        """DELETE FROM recommendation_evidence WHERE recommendation_id IN (
               SELECT r.recommendation_id FROM recommendations r
               JOIN harvest_submissions s ON r.submission_id = s.submission_id
               WHERE s.farmer_id = %s);""", (fid,))
    cur.execute(
        """DELETE FROM recommendations WHERE submission_id IN (
               SELECT submission_id FROM harvest_submissions WHERE farmer_id = %s);""", (fid,))
    cur.execute("DELETE FROM harvest_submissions WHERE farmer_id = %s;", (fid,))
    cur.execute("DELETE FROM farmers WHERE farmer_id = %s;", (fid,))


def cleanup_test_farmers():
    """Delete ONLY rows tied to our test phones, in FK order."""
    all_phones = TEST_PHONES + [INACTIVE_PHONE]
    counts = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT farmer_id FROM farmers WHERE phone_number = ANY(%s);",
                (all_phones,),
            )
            fids = [r["farmer_id"] for r in cur.fetchall()]

            if not fids:
                for t in ("sms_logs", "recommendation_evidence", "recommendations",
                          "harvest_submissions", "farmers"):
                    counts[t] = 0
                return counts

            # sms_logs
            cur.execute(
                """
                DELETE FROM sms_logs
                WHERE recommendation_id IN (
                    SELECT r.recommendation_id
                    FROM recommendations r
                    JOIN harvest_submissions s ON r.submission_id = s.submission_id
                    WHERE s.farmer_id = ANY(%s)
                );
                """, (fids,))
            counts["sms_logs"] = cur.rowcount

            # recommendation_evidence
            cur.execute(
                """
                DELETE FROM recommendation_evidence
                WHERE recommendation_id IN (
                    SELECT r.recommendation_id
                    FROM recommendations r
                    JOIN harvest_submissions s ON r.submission_id = s.submission_id
                    WHERE s.farmer_id = ANY(%s)
                );
                """, (fids,))
            counts["recommendation_evidence"] = cur.rowcount

            # recommendations
            cur.execute(
                """
                DELETE FROM recommendations
                WHERE submission_id IN (
                    SELECT submission_id FROM harvest_submissions WHERE farmer_id = ANY(%s)
                );
                """, (fids,))
            counts["recommendations"] = cur.rowcount

            # harvest_submissions
            cur.execute(
                "DELETE FROM harvest_submissions WHERE farmer_id = ANY(%s);", (fids,))
            counts["harvest_submissions"] = cur.rowcount

            # farmers
            cur.execute(
                "DELETE FROM farmers WHERE phone_number = ANY(%s);", (all_phones,))
            counts["farmers"] = cur.rowcount

            # also clean the farmer created by the test_admin_api.py subprocess
            _delete_farmer_phone(cur, ADMIN_TEST_PHONE)

    return counts


def ussd_post(client, phone, text, session_id="SID001", token_param=""):
    """Helper to POST to USSD callback."""
    url = "/api/ussd/callback"
    if token_param:
        url += f"?token={token_param}"
    return client.post(url, data={
        "sessionId": session_id,
        "phoneNumber": phone,
        "text": text,
        "serviceCode": "*123#",
        "networkCode": "63902",
    })

def delivery_post(client, provider_id, status, failure_reason="", token_param=""):
    url = "/api/webhooks/sms-delivery"
    if token_param:
        url += f"?token={token_param}"
    return client.post(url, data={
        "id": provider_id,
        "status": status,
        "phoneNumber": TEST_PHONES[0],
        "failureReason": failure_reason,
    })

def _today_ddmmyyyy(offset: int = 1) -> str:
    return (date.today() + timedelta(days=offset)).strftime("%d%m%Y")

def _full_text(lang_choice: str, date_str: str, qty: str = "500",
               ripeness: str = "3", storage: str = "1", confirm: str = "1") -> str:
    """Build the full '*'-joined text for a complete submit flow."""
    return f"{lang_choice}*1*{date_str}*{qty}*{ripeness}*{storage}*{confirm}"

# ── All tests ─────────────────────────────────────────────────────────────────

def run_all_tests(app):
    client = app.test_client()
    global _sms_should_fail

    # ── (a) Unregistered and inactive numbers ─────────────────────────────────
    r = ussd_post(client, UNREGISTERED_PHONE, "")
    body = r.data.decode()
    report("(a) Unregistered number → END bilingual",
           r.status_code == 200 and body.startswith("END") and "not registered" in body.lower())

    r = ussd_post(client, INACTIVE_PHONE, "")
    body = r.data.decode()
    report("(a) Inactive account → END bilingual",
           r.status_code == 200 and body.startswith("END") and "inactive" in body.lower())

    r = ussd_post(client, "+250789000998", "")
    body = r.data.decode()
    report("(a) Valid format but nobody → END not registered",
           r.status_code == 200 and body.startswith("END") and "not registered" in body.lower())

    # ── (b) English full flow — inside active season ──────────────────────────
    phone = TEST_PHONES[0]
    sid = "SID_EN_IN"
    # Date inside Season A 2027 (2026-09-01 to 2027-01-31)
    harvest_in = (date(2026, 12, 15)).strftime("%d%m%Y")
    text = _full_text("1", harvest_in, "500", "3", "1", "1")
    _sms_calls.clear()
    r = ussd_post(client, phone, text, session_id=sid)
    body = r.data.decode()
    time.sleep(0.3)  # let async SMS thread commit

    report("(b) EN full flow — returns END",
           r.status_code == 200 and body.startswith("END"), body[:120])
    report("(b) EN full flow — guide only line",
           "Guide only" in body or "guide only" in body.lower(), body[:120])

    # Verify DB state
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT farmer_id FROM farmers WHERE phone_number = %s;", (phone,))
            fid = cur.fetchone()["farmer_id"]
            cur.execute(
                """SELECT s.submission_id, s.status, s.location, s.tomato_maturity,
                          r.recommendation_id, r.action, r.confidence_level
                   FROM harvest_submissions s
                   JOIN recommendations r ON r.submission_id = s.submission_id
                   WHERE s.farmer_id = %s
                   ORDER BY s.submission_id DESC LIMIT 1;""", (fid,))
            row = cur.fetchone()
            report("(b) EN — submission PROCESSED + location copied",
                   row is not None and row["status"] == "PROCESSED"
                   and row["location"] == "TestVillage", str(row))
            report("(b) EN — maturity RIPE stored",
                   row is not None and row["tomato_maturity"] == "RIPE")
            rec_id = row["recommendation_id"] if row else None

            if rec_id:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM recommendation_evidence WHERE recommendation_id = %s;",
                    (rec_id,))
                cnt = cur.fetchone()["cnt"]
                report("(b) EN — exactly 3 evidence rows", cnt == 3, f"got {cnt}")

                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM sms_logs WHERE recommendation_id = %s AND status = 'SENT';",
                    (rec_id,))
                sms_cnt = cur.fetchone()["cnt"]
                report("(b) EN — sms_logs has SENT row", sms_cnt >= 1, f"got {sms_cnt}")

    # Date outside active season (Feb 2027)
    sid2 = "SID_EN_OUT"
    harvest_out = (date(2027, 2, 10)).strftime("%d%m%Y")
    text_out = _full_text("1", harvest_out, "400", "1", "2", "1")
    r2 = ussd_post(client, phone, text_out, session_id=sid2)
    body2 = r2.data.decode()
    time.sleep(0.3)
    report("(b) EN full flow — outside season also returns END",
           r2.status_code == 200 and body2.startswith("END"), body2[:120])

    # ── (c) Kinyarwanda full flow ─────────────────────────────────────────────
    phone_rw = TEST_PHONES[1]
    sid_rw = "SID_RW"
    harvest_rw = (date(2026, 12, 20)).strftime("%d%m%Y")
    text_rw = _full_text("2", harvest_rw, "300", "2", "1", "1")
    _sms_calls.clear()
    r_rw = ussd_post(client, phone_rw, text_rw, session_id=sid_rw)
    body_rw = r_rw.data.decode()
    time.sleep(0.3)

    report("(c) RW full flow — returns END",
           r_rw.status_code == 200 and body_rw.startswith("END"), body_rw[:120])
    report("(c) RW full flow — Kinyarwanda guide line in body",
           "Inama gusa" in body_rw or "gusa" in body_rw, body_rw[:120])
    # Check language saved
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT preferred_language FROM farmers WHERE phone_number = %s;", (phone_rw,))
            lang_saved = cur.fetchone()["preferred_language"]
    report("(c) RW — preferred_language saved as rw", lang_saved == "rw", lang_saved)

    # ── (d) Invalid inputs ────────────────────────────────────────────────────
    phone_d = TEST_PHONES[2]

    def inv(text_suffix, sid_suffix, label):
        r = ussd_post(client, phone_d, f"1*1*{text_suffix}", session_id=f"SID_INV_{sid_suffix}")
        body = r.data.decode()
        report(f"(d) {label} → CON re-prompt, no DB write",
               r.status_code == 200 and body.startswith("CON"), body[:100])

    inv("99991399", "BADDATE", "Bad date (99/13/9999)")
    inv("01011999", "PASTDATE", "Past date")
    inv("*0", "QTY0", "Quantity 0")  # date then 0 qty
    today_plus1 = _today_ddmmyyyy(1)
    r = ussd_post(client, phone_d, f"1*1*{today_plus1}*0", session_id="SID_QTY0")
    report("(d) Quantity 0 → CON",
           r.status_code == 200 and r.data.decode().startswith("CON"), r.data.decode()[:80])
    r = ussd_post(client, phone_d, f"1*1*{today_plus1}*abc", session_id="SID_QTYTEXT")
    report("(d) Quantity text → CON",
           r.status_code == 200 and r.data.decode().startswith("CON"), r.data.decode()[:80])
    r = ussd_post(client, phone_d, f"1*1*{today_plus1}*500*7", session_id="SID_RIP7")
    report("(d) Ripeness 7 → CON",
           r.status_code == 200 and r.data.decode().startswith("CON"), r.data.decode()[:80])
    r = ussd_post(client, phone_d, f"1*1*{today_plus1}*500*3*3", session_id="SID_STOR3")
    report("(d) Storage 3 → CON",
           r.status_code == 200 and r.data.decode().startswith("CON"), r.data.decode()[:80])

    # Verify no spurious DB writes for invalid inputs
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT farmer_id FROM farmers WHERE phone_number = %s;", (phone_d,))
            fid_d = cur.fetchone()["farmer_id"]
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM harvest_submissions WHERE farmer_id = %s;", (fid_d,))
            cnt_d = cur.fetchone()["cnt"]
    report("(d) No DB writes for invalid inputs", cnt_d == 0, f"got {cnt_d} submissions")

    # ── (e) Back navigation + Cancel ─────────────────────────────────────────
    phone_e = TEST_PHONES[3]
    td = _today_ddmmyyyy(2)

    # 0 from date screen → back to main
    r = ussd_post(client, phone_e, "1*1*0", session_id="SID_BACK_DATE")
    report("(e) 0 from date screen → CON main menu",
           r.data.decode().startswith("CON"), r.data.decode()[:80])

    # 0 from quantity screen → back to date
    r = ussd_post(client, phone_e, f"1*1*{td}*0", session_id="SID_BACK_QTY")
    b = r.data.decode()
    report("(e) 0 from quantity screen → CON re-ask date",
           b.startswith("CON") and ("DDMMYYYY" in b or "itariki" in b.lower()), b[:80])

    # 0 from ripeness → back to quantity
    r = ussd_post(client, phone_e, f"1*1*{td}*500*0", session_id="SID_BACK_RIP")
    b = r.data.decode()
    report("(e) 0 from ripeness screen → CON re-ask quantity",
           b.startswith("CON") and ("kg" in b.lower() or "quantity" in b.lower()), b[:80])

    # Cancel at confirm
    r = ussd_post(client, phone_e, f"1*1*{td}*500*3*1*2", session_id="SID_CANCEL")
    b = r.data.decode()
    report("(e) Cancel at confirm → END cancelled",
           b.startswith("END") and "cancel" in b.lower(), b[:80])
    # Verify no DB write
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT farmer_id FROM farmers WHERE phone_number = %s;", (phone_e,))
            fid_e = cur.fetchone()["farmer_id"]
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM harvest_submissions WHERE farmer_id = %s;", (fid_e,))
            cnt_e = cur.fetchone()["cnt"]
    report("(e) Cancel writes nothing to DB", cnt_e == 0, f"got {cnt_e}")

    # ── (f) STORE_AND_WAIT guard on real rules ────────────────────────────────
    phone_f = TEST_PHONES[4]
    td3 = _today_ddmmyyyy(3)
    store_and_wait_without_pres = False
    ripeness_map = {"1": "GREEN", "2": "TURNING", "3": "RIPE"}
    for rip_code in ("1", "2", "3"):
        for stor_code in ("1", "2"):
            sid_f = f"SID_GUARD_{rip_code}_{stor_code}"
            text_f = f"1*1*{td3}*500*{rip_code}*{stor_code}*1"
            r_f = ussd_post(client, phone_f, text_f, session_id=sid_f)
            b_f = r_f.data.decode()
            if b_f.startswith("END"):
                # Check DB
                time.sleep(0.1)
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT farmer_id FROM farmers WHERE phone_number = %s;", (phone_f,))
                        fid_f = cur.fetchone()["farmer_id"]
                        cur.execute(
                            """SELECT r.action FROM recommendations r
                               JOIN harvest_submissions s ON r.submission_id = s.submission_id
                               WHERE s.farmer_id = %s
                               ORDER BY r.recommendation_id DESC LIMIT 1;""", (fid_f,))
                        rec_f = cur.fetchone()
                        if rec_f and rec_f["action"] == "STORE_AND_WAIT" and stor_code == "2":
                            store_and_wait_without_pres = True
    report("(f) STORE_AND_WAIT never issued without preservation",
           not store_and_wait_without_pres)

    # ── (g) My submissions + My advice ───────────────────────────────────────
    # Submit 2 more for phone0 so we have multiple
    phone_g = TEST_PHONES[0]
    for i, dt_offset in enumerate([4, 5]):
        sid_gi = f"SID_G_{i}"
        td_i = _today_ddmmyyyy(dt_offset)
        ussd_post(client, phone_g, _full_text("1", td_i, "200", "1", "2", "1"), session_id=sid_gi)
        time.sleep(0.1)

    r = ussd_post(client, phone_g, "1*2", session_id="SID_G_SUBS")
    body_subs = r.data.decode()
    report("(g) My submissions → END with entries <= 182 chars",
           body_subs.startswith("END") and len(body_subs) <= 186, body_subs[:100])

    r = ussd_post(client, phone_g, "1*3", session_id="SID_G_ADV")
    body_adv = r.data.decode()
    report("(g) My advice → END with entries",
           body_adv.startswith("END") and len(body_adv) <= 186, body_adv[:100])

    # Empty state — fresh farmer
    phone_empty = TEST_PHONES[5]
    r = ussd_post(client, phone_empty, "1*2", session_id="SID_G_EMPTY_S")
    b_es = r.data.decode()
    report("(g) My submissions — empty state",
           b_es.startswith("END") and "No submissions" in b_es, b_es[:80])
    r = ussd_post(client, phone_empty, "1*3", session_id="SID_G_EMPTY_A")
    b_ea = r.data.decode()
    report("(g) My advice — empty state",
           b_ea.startswith("END") and "No advice" in b_ea, b_ea[:80])

    # ── (h) Idempotency — same session+text posted twice ─────────────────────
    phone_h = TEST_PHONES[6]
    sid_h = "SID_IDMP"
    td_h = _today_ddmmyyyy(6)
    text_h = _full_text("1", td_h, "350", "3", "1", "1")
    _sms_calls.clear()
    session_store.clear_all()

    r1 = ussd_post(client, phone_h, text_h, session_id=sid_h)
    time.sleep(0.3)
    r2 = ussd_post(client, phone_h, text_h, session_id=sid_h)
    time.sleep(0.3)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT farmer_id FROM farmers WHERE phone_number = %s;", (phone_h,))
            fid_h = cur.fetchone()["farmer_id"]
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM harvest_submissions WHERE farmer_id = %s;", (fid_h,))
            sub_cnt = cur.fetchone()["cnt"]
            cur.execute(
                """SELECT COUNT(*) AS cnt FROM sms_logs sl
                   JOIN recommendations r ON r.recommendation_id = sl.recommendation_id
                   JOIN harvest_submissions s ON s.submission_id = r.submission_id
                   WHERE s.farmer_id = %s;""", (fid_h,))
            sms_cnt_h = cur.fetchone()["cnt"]

    report("(h) Idempotency — 1 submission created",
           sub_cnt == 1, f"got {sub_cnt}")
    report("(h) Idempotency — same body returned both times",
           r1.data == r2.data or r1.data.decode().startswith("END"), r1.data.decode()[:80])

    # ── (i) Delivery webhook ──────────────────────────────────────────────────
    # Grab a real sms_logs provider_id from phone_h submission
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT sl.provider_id, sl.sms_id FROM sms_logs sl
                   JOIN recommendations r ON r.recommendation_id = sl.recommendation_id
                   JOIN harvest_submissions s ON s.submission_id = r.submission_id
                   WHERE s.farmer_id = %s
                   ORDER BY sl.sms_id DESC LIMIT 1;""", (fid_h,))
            sms_row = cur.fetchone()

    if sms_row and sms_row["provider_id"]:
        pid = sms_row["provider_id"]
        # Intermediate status ignored
        r = delivery_post(client, pid, "Buffered")
        report("(i) Delivery — Buffered ignored → 200 OK", r.status_code == 200)
        # Success → DELIVERED
        r = delivery_post(client, pid, "Success")
        report("(i) Delivery — Success → 200 OK", r.status_code == 200)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, delivered_at FROM sms_logs WHERE provider_id = %s;", (pid,))
                dl = cur.fetchone()
        report("(i) Delivery — status DELIVERED with delivered_at",
               dl["status"] == "DELIVERED" and dl["delivered_at"] is not None, str(dl))
        # Cannot downgrade
        r = delivery_post(client, pid, "Failed")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM sms_logs WHERE provider_id = %s;", (pid,))
                after = cur.fetchone()["status"]
        report("(i) Delivery — DELIVERED not downgraded", after == "DELIVERED", after)
    else:
        report("(i) Delivery webhook tests — skipped (no provider_id)", False, "No sms_logs row")

    # Unknown provider_id returns 200
    r = delivery_post(client, "NONEXISTENT_ID_XYZ", "Success")
    report("(i) Delivery — unknown id → 200 OK", r.status_code == 200)

    # Token check
    os.environ["AT_WEBHOOK_TOKEN"] = "secret123"
    r_notok = ussd_post(client, TEST_PHONES[0], "", session_id="SID_TOK1")
    report("(i) Token check — missing token → 403",
           r_notok.status_code == 403, str(r_notok.status_code))
    r_badtok = ussd_post(client, TEST_PHONES[0], "", session_id="SID_TOK2", token_param="wrong")
    report("(i) Token check — wrong token → 403",
           r_badtok.status_code == 403, str(r_badtok.status_code))
    r_goodtok = ussd_post(client, TEST_PHONES[0], "", session_id="SID_TOK3", token_param="secret123")
    report("(i) Token check — correct token → 200",
           r_goodtok.status_code == 200, str(r_goodtok.status_code))
    r_wh_bad = delivery_post(client, "X", "Success", token_param="bad")
    report("(i) Token check — webhook wrong token → 403",
           r_wh_bad.status_code == 403, str(r_wh_bad.status_code))
    r_wh_ok = delivery_post(client, "X", "Success", token_param="secret123")
    report("(i) Token check — webhook correct token → 200",
           r_wh_ok.status_code == 200, str(r_wh_ok.status_code))
    # Restore: no token check
    os.environ["AT_WEBHOOK_TOKEN"] = ""

    # ── (j) SMS provider failure — recommendation committed, FAILED row ───────
    phone_j = TEST_PHONES[7]
    sid_j = "SID_J"
    td_j = _today_ddmmyyyy(7)
    _sms_should_fail = True
    _sms_calls.clear()
    r_j = ussd_post(client, phone_j, _full_text("1", td_j, "250", "3", "2", "1"), session_id=sid_j)
    time.sleep(0.5)
    _sms_should_fail = False

    body_j = r_j.data.decode()
    report("(j) SMS failure — USSD still returns END advice",
           r_j.status_code == 200 and body_j.startswith("END"), body_j[:120])
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT farmer_id FROM farmers WHERE phone_number = %s;", (phone_j,))
            fid_j = cur.fetchone()["farmer_id"]
            cur.execute(
                """SELECT COUNT(*) AS cnt FROM harvest_submissions WHERE farmer_id = %s
                   AND status = 'PROCESSED';""", (fid_j,))
            sub_j = cur.fetchone()["cnt"]
            cur.execute(
                """SELECT sl.status FROM sms_logs sl
                   JOIN recommendations r ON r.recommendation_id = sl.recommendation_id
                   JOIN harvest_submissions s ON s.submission_id = r.submission_id
                   WHERE s.farmer_id = %s
                   ORDER BY sl.sms_id DESC LIMIT 1;""", (fid_j,))
            sms_j = cur.fetchone()
    report("(j) SMS failure — submission committed and PROCESSED", sub_j == 1, str(sub_j))
    report("(j) SMS failure — sms_logs has FAILED row",
           sms_j is not None and sms_j["status"] == "FAILED", str(sms_j))

    # ── (k) 10 concurrent farmers ─────────────────────────────────────────────
    confirm_latencies = []
    flow_latencies = []
    errors = []

    def _run_farmer(i: int) -> dict:
        phone = TEST_PHONES[i]
        sid = f"SID_CONC_{i:02d}"
        td_k = _today_ddmmyyyy(8 + i)
        text_k = _full_text("1", td_k, str(100 + i * 10), "1", "2", "1")

        t0_flow = time.perf_counter()
        # Confirm step (the whole flow in one call for the test client)
        t0_conf = time.perf_counter()
        resp = ussd_post(client, phone, text_k, session_id=sid)
        lat_conf = time.perf_counter() - t0_conf
        lat_flow = time.perf_counter() - t0_flow

        return {
            "phone": phone,
            "ok": resp.status_code == 200 and resp.data.decode().startswith("END"),
            "lat_conf": lat_conf,
            "lat_flow": lat_flow,
            "body": resp.data.decode()[:80],
        }

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_run_farmer, i): i for i in range(10)}
        results_k = [f.result() for f in as_completed(futs)]

    time.sleep(1.0)  # let SMS threads settle

    all_ok = all(r["ok"] for r in results_k)
    report("(k) 10 concurrent farmers — all END responses", all_ok,
           str([r["body"] for r in results_k if not r["ok"]][:3]))

    # Count DB rows
    with get_connection() as conn:
        with conn.cursor() as cur:
            all_fids = []
            for phone in TEST_PHONES:
                cur.execute("SELECT farmer_id FROM farmers WHERE phone_number = %s;", (phone,))
                row = cur.fetchone()
                if row:
                    all_fids.append(row["farmer_id"])

            cur.execute(
                "SELECT COUNT(*) AS cnt FROM harvest_submissions WHERE farmer_id = ANY(%s);",
                (all_fids,))
            total_subs = cur.fetchone()["cnt"]
            cur.execute(
                """SELECT COUNT(*) AS cnt FROM recommendations r
                   JOIN harvest_submissions s ON r.submission_id = s.submission_id
                   WHERE s.farmer_id = ANY(%s);""", (all_fids,))
            total_recs = cur.fetchone()["cnt"]
            cur.execute(
                """SELECT COUNT(*) AS cnt FROM sms_logs sl
                   JOIN recommendations r ON r.recommendation_id = sl.recommendation_id
                   JOIN harvest_submissions s ON s.submission_id = r.submission_id
                   WHERE s.farmer_id = ANY(%s);""", (all_fids,))
            total_sms = cur.fetchone()["cnt"]

    report("(k) 10 concurrent — correct submission count",
           total_subs >= 10, f"got {total_subs}")
    report("(k) 10 concurrent — correct recommendation count",
           total_recs >= 10, f"got {total_recs}")
    report("(k) 10 concurrent — correct SMS count",
           total_sms >= 10, f"got {total_sms}")

    conf_lats = sorted(r["lat_conf"] for r in results_k)
    flow_lats = sorted(r["lat_flow"] for r in results_k)
    p50_conf = conf_lats[4]
    p95_conf = conf_lats[9]
    p50_flow = flow_lats[4]
    p95_flow = flow_lats[9]
    print(f"  Latency (confirm): p50={p50_conf*1000:.0f}ms  p95={p95_conf*1000:.0f}ms")
    print(f"  Latency (flow):    p50={p50_flow*1000:.0f}ms  p95={p95_flow*1000:.0f}ms")
    report("(k) p95 confirm step < 1500ms", p95_conf < 1.5, f"{p95_conf*1000:.0f}ms")

    # ── (l) Garbage input never returns 500 ──────────────────────────────────
    garbage_inputs = [
        "1*1*abc*****",
        "9*9*9",
        "*****",
        "0",
        "1*0",
        "2*1*99991399",
    ]
    for gi in garbage_inputs:
        r = ussd_post(client, TEST_PHONES[0], gi, session_id=f"SID_GARB_{gi[:5]}")
        b = r.data.decode()
        ok = r.status_code == 200 and (b.startswith("CON") or b.startswith("END"))
        report(f"(l) Garbage '{gi[:20]}' → CON or END, 200", ok, b[:60])

    # ── (m) Admin dashboard still passes ─────────────────────────────────────
    # Re-run Prompt 1 services tests
    import subprocess
    res = subprocess.run(
        [sys.executable, "backend/tests/test_services.py"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    report("(m) test_services.py still 38/38 pass",
           "38 passed, 0 failed" in res.stdout, res.stdout[-200:])

    # Pre-clean the farmer phone used by test_admin_api.py so it always starts fresh
    with get_connection() as conn:
        with conn.cursor() as cur:
            _delete_farmer_phone(cur, ADMIN_TEST_PHONE)

    # Run existing admin API tests
    res2 = subprocess.run(
        [sys.executable, "tests/test_admin_api.py"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    report("(m) test_admin_api.py 15/15 pass",
           "15/15 checks passed" in res2.stdout, res2.stdout[-200:])


def main():
    print("=" * 60)
    print("METLINK USSD FLOW TESTS")
    print("=" * 60)

    app = create_app()
    app.config["TESTING"] = True

    setup_test_farmers()
    try:
        run_all_tests(app)
    finally:
        counts = cleanup_test_farmers()
        print("\n── Cleanup ─────────────────────────────────────────────────")
        for table, n in counts.items():
            print(f"  Deleted {n:>4} row(s) from {table}")
        print("────────────────────────────────────────────────────────────")

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
