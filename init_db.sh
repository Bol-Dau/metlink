#!/usr/bin/env bash
set -e

if [ ! -f .env ]; then
    echo "Error: .env file not found."
    exit 1
fi

set -a
source <(tr -d '\r' < .env)
set +a

export PGPASSWORD="$DB_PASSWORD"

echo "Wiping and rebuilding $DB_NAME as $DB_USER..."

psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f database/schema.sql
psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f database/indexes.sql
psql -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f database/seed.sql

unset PGPASSWORD
echo "Done. $DB_NAME is clean and seeded."

python3 -c "from backend.auth import hash_password; from database.connector import get_cursor; cur_ctx = get_cursor(); cur = cur_ctx.__enter__(); cur.execute('UPDATE admins SET password_hash = %s WHERE username = %s;', (hash_password('Admin@1234'), 'aline.uwase')); cur.execute('UPDATE admins SET password_hash = %s WHERE username = %s;', (hash_password('Analyst@1234'), 'eric.mugisha')); cur_ctx.__exit__(None, None, None); print('Admin passwords ready!')"
python3 -c "from backend.auth import hash_password; from database.connector import get_cursor; cur_ctx = get_cursor(); cur = cur_ctx.__enter__(); cur.execute('UPDATE admins SET password_hash = %s WHERE username = %s;', (hash_password('Analyst@1234'), 'eric.mugisha')); cur_ctx.__exit__(None, None, None); print('Updated eric.mugisha password to: Analyst@1234')"
