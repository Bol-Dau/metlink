-- ============================================================================
-- Runs schema.sql, indexes.sql, and seed.sql in order.
-- Uses \ir so it always finds the files inside the database/ folder
-- no matter which directory you opened psql from.
-- ============================================================================

\set ON_ERROR_STOP on

\echo '1/3 Creating tables and constraints (schema.sql)...'
\ir schema.sql

\echo '2/3 Creating indexes (indexes.sql)...'
\ir indexes.sql

\echo '3/3 Loading Kamonyi tomato seed data (seed.sql)...'
\ir seed.sql

\echo 'Done! All 10 tables, 19 indexes, and seed records are ready.'