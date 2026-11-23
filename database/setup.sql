-- database/setup.sql
-- Run once on a new machine: psql -U postgres -f database/setup.sql
SELECT 'CREATE DATABASE metlink_db ENCODING ''UTF8'''
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'metlink_db')\gexec