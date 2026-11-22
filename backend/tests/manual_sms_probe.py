"""
Direct Africa's Talking SMS Probe for METLINK Sandbox.

Usage:
  python backend/tests/manual_sms_probe.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 1. Load .env first
from database.connector import _load_dotenv_if_present, get_cursor
_load_dotenv_if_present()

from backend.services.sms_service import (
    default_sms_provider,
    get_sms_config,
    send_sms_sync,
)

TARGET_PHONE = "+250788419204"
TEST_MESSAGE = "METLINK sandbox test. Please ignore."


def main():
    print("=" * 60)
    print("METLINK DIRECT AFRICA'S TALKING SMS PROBE")
    print("=" * 60)

    # 3. Print resolved mode first
    config = get_sms_config()
    mode = config["mode"]
    print(f"Resolved SMS Mode: {mode}")
    print(f"Username configured: {config['username']}")
    print(f"API Key present: {bool(config['api_key'])}")
    print(f"Sender ID configured: {config['sender_id']}")

    if mode != "live":
        print(f"ERROR: SMS mode is '{mode}' (not 'live'). Cannot run live probe.")
        sys.exit(1)

    # 1. Call provider directly (no DB write)
    print("\n--- Part 1: Direct Provider SDK Call (No DB Write) ---")
    try:
        provider_result = default_sms_provider(TARGET_PHONE, TEST_MESSAGE)
        raw_json = provider_result.get("raw_response", {})
        print("Raw JSON Response from Africa's Talking:")
        print(json.dumps(raw_json, indent=2))

        print("\nParsed Result:")
        print(f"  Recipient Status: {provider_result.get('status')}")
        print(f"  Status Code:      {provider_result.get('status_code')}")
        print(f"  Message ID:       {provider_result.get('provider_id')}")
    except Exception as exc:
        print(f"Provider call failed: {exc}")
        sys.exit(1)

    # 4. Send ONE message through send_sms_sync with real latest recommendation_id
    print("\n--- Part 2: Integrated send_sms_sync Call (Writes to sms_logs) ---")
    latest_rec_id = None
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT recommendation_id, action, created_at
            FROM recommendations
            ORDER BY recommendation_id DESC
            LIMIT 1;
            """
        )
        row = cur.fetchone()
        if row:
            latest_rec_id = row["recommendation_id"]

    if not latest_rec_id:
        print("ERROR: No recommendation found in database to link sms_logs.")
        sys.exit(1)

    print(f"Using latest recommendation_id: {latest_rec_id}")
    sync_result = send_sms_sync(latest_rec_id, TARGET_PHONE, TEST_MESSAGE)
    print(f"send_sms_sync return value: {sync_result}")

    # Query the resulting sms_logs row
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT sms_id, recommendation_id, phone_number, status, provider_id, sent_at
            FROM sms_logs
            WHERE recommendation_id = %s
            ORDER BY sms_id DESC
            LIMIT 1;
            """,
            (latest_rec_id,),
        )
        log_row = cur.fetchone()

    print("\nResulting sms_logs row in Database:")
    if log_row:
        print(f"  SMS ID:      {log_row['sms_id']}")
        print(f"  Status:      {log_row['status']}")
        print(f"  Provider ID: {log_row['provider_id']}")
        print(f"  Sent At:     {log_row['sent_at']}")
    else:
        print("  ERROR: No sms_logs row found!")
        sys.exit(1)

    print("\nProbe completed successfully.")


if __name__ == "__main__":
    main()
