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
