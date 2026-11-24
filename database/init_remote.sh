#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# METLINK Remote Database Initialization Script
# Usage: ./init_remote.sh --yes [--reset]
# ==============================================================================

CONFIRMED=false
RESET=false

for arg in "$@"; do
    case "$arg" in
        --yes)
            CONFIRMED=true
            ;;
        --reset)
            RESET=true
            ;;
        -h|--help)
            echo "Usage: $0 --yes [--reset]"
            echo "  --yes    Required confirmation flag to perform initialization"
            echo "  --reset  Drop and recreate public schema if tables already exist"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 --yes [--reset]"
            exit 1
            ;;
    esac
done

if [ "$CONFIRMED" != "true" ]; then
    echo "Error: Execution requires explicit confirmation flag --yes"
    echo "Usage: $0 --yes [--reset]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Check for psql client
if ! command -v psql >/dev/null 2>&1; then
    echo "Error: 'psql' client utility is not installed or not in PATH."
    exit 1
fi

# Load DATABASE_URL from environment or local .env
if [ -z "${DATABASE_URL:-}" ]; then
    if [ -f "$REPO_ROOT/.env" ]; then
        # Read DATABASE_URL from .env without printing or exporting everything blindly
        DATABASE_URL="$(grep -E '^DATABASE_URL=' "$REPO_ROOT/.env" | cut -d'=' -f2- | tr -d '\r' | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//' || true)"
    fi
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "Error: DATABASE_URL is not set in environment or .env file."
    exit 1
fi

export DATABASE_URL

# Validate admin credentials before touching database
SUPER_ADMIN_PW="${SEED_SUPER_ADMIN_PASSWORD:-}"
ANALYST_PW="${SEED_ANALYST_PASSWORD:-}"

USE_DEFAULT_SUPER=false
USE_DEFAULT_ANALYST=false

if [ -z "$SUPER_ADMIN_PW" ]; then
    USE_DEFAULT_SUPER=true
    SUPER_ADMIN_PW="Admin@1234"
else
    PW_LEN=${#SUPER_ADMIN_PW}
    if [ "$PW_LEN" -lt 8 ] || [ "$PW_LEN" -gt 72 ]; then
        echo "Error: SEED_SUPER_ADMIN_PASSWORD must be between 8 and 72 bytes."
        exit 1
    fi
fi

if [ -z "$ANALYST_PW" ]; then
    USE_DEFAULT_ANALYST=true
    ANALYST_PW="Analyst@1234"
else
    PW_LEN=${#ANALYST_PW}
    if [ "$PW_LEN" -lt 8 ] || [ "$PW_LEN" -gt 72 ]; then
        echo "Error: SEED_ANALYST_PASSWORD must be between 8 and 72 bytes."
        exit 1
    fi
fi

# Check if METLINK tables already exist
TABLE_COUNT=$(psql "$DATABASE_URL" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('admins', 'farmers', 'decision_rules');" 2>/dev/null || echo "0")

if [ "$TABLE_COUNT" -gt 0 ]; then
    if [ "$RESET" = "true" ]; then
        echo "Resetting public schema on remote database..."
        psql -v ON_ERROR_STOP=1 "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null
    else
        echo "Error: METLINK database tables already exist in public schema."
        echo "To drop and reinitialize existing tables, re-run with --reset:"
        echo "  $0 --yes --reset"
        exit 1
    fi
fi

echo "Applying schema definitions..."
psql -v ON_ERROR_STOP=1 "$DATABASE_URL" -f "$SCRIPT_DIR/schema.sql" >/dev/null

echo "Applying database indexes..."
psql -v ON_ERROR_STOP=1 "$DATABASE_URL" -f "$SCRIPT_DIR/indexes.sql" >/dev/null

echo "Applying baseline seed data..."
psql -v ON_ERROR_STOP=1 "$DATABASE_URL" -f "$SCRIPT_DIR/seed.sql" >/dev/null

if [ "$USE_DEFAULT_SUPER" = "true" ] || [ "$USE_DEFAULT_ANALYST" = "true" ]; then
    echo "================================================================================"
    echo "SECURITY WARNING: SEED_*_PASSWORD environment variables not provided."
    echo "Default seed credentials were used. Rotate these passwords immediately in production!"
    echo "================================================================================"
fi

# Set admin password hashes via backend auth utility securely
export METLINK_INIT_SUPER_PW="$SUPER_ADMIN_PW"
export METLINK_INIT_ANALYST_PW="$ANALYST_PW"

PYTHONPATH="$REPO_ROOT" python3 - << 'EOF'
import os
import sys
from backend.auth import hash_password
from database.connector import get_cursor

super_pw = os.environ.get("METLINK_INIT_SUPER_PW")
analyst_pw = os.environ.get("METLINK_INIT_ANALYST_PW")

if not super_pw or not analyst_pw:
    print("Error: Initialization passwords missing in execution context", file=sys.stderr)
    sys.exit(1)

super_hash = hash_password(super_pw)
analyst_hash = hash_password(analyst_pw)

with get_cursor() as cur:
    cur.execute("UPDATE admins SET password_hash = %s WHERE username = %s;", (super_hash, "aline.uwase"))
    cur.execute("UPDATE admins SET password_hash = %s WHERE username = %s;", (analyst_hash, "eric.mugisha"))

print("Admin credentials configured successfully.")
EOF

unset METLINK_INIT_SUPER_PW
unset METLINK_INIT_ANALYST_PW

echo "Remote database initialization completed successfully."
