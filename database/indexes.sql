-- ============================================================================
-- METLINK Database Indexes (indexes.sql)
-- Speeds up common dashboard queries, USSD lookups, and foreign key joins.
-- ============================================================================

BEGIN;

-- 1. Harvest Submissions: Lookup farmer history, upcoming harvests, and status
CREATE INDEX IF NOT EXISTS idx_submissions_farmer_created
    ON harvest_submissions(farmer_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_submissions_expected_date
    ON harvest_submissions(expected_harvest_date);

CREATE INDEX IF NOT EXISTS idx_submissions_status
    ON harvest_submissions(status);

-- 2. Decision Rules: Fetch active rules in priority order
CREATE INDEX IF NOT EXISTS idx_rules_active_priority
    ON decision_rules(is_active, priority);

-- 3. Market Information: Latest prices by location
CREATE INDEX IF NOT EXISTS idx_market_location_created
    ON market_information(location, created_at DESC);

-- 4. Seasonal Information: Active season date checks
CREATE INDEX IF NOT EXISTS idx_seasons_dates
    ON seasonal_information(start_date, end_date);

-- 5. Recommendations & Evidence: Fast joins for dashboard audit views
CREATE INDEX IF NOT EXISTS idx_recommendations_rule_id
    ON recommendations(decision_rule_id);

CREATE INDEX IF NOT EXISTS idx_evidence_recommendation_id
    ON recommendation_evidence(recommendation_id);

CREATE INDEX IF NOT EXISTS idx_evidence_market_id
    ON recommendation_evidence(market_information_id);

CREATE INDEX IF NOT EXISTS idx_evidence_seasonal_id
    ON recommendation_evidence(seasonal_information_id);

-- 6. SMS Logs: Delivery tracking, farmer SMS history, and provider receipt lookup
CREATE INDEX IF NOT EXISTS idx_sms_phone_sent
    ON sms_logs(phone_number, sent_at DESC);

CREATE INDEX IF NOT EXISTS idx_sms_status
    ON sms_logs(status);

CREATE INDEX IF NOT EXISTS idx_sms_recommendation_id
    ON sms_logs(recommendation_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sms_provider_id_unique
    ON sms_logs(provider_id)
    WHERE provider_id IS NOT NULL;

-- 7. Audit Logs: Admin activity feed and record history
CREATE INDEX IF NOT EXISTS idx_audit_admin_created
    ON audit_logs(admin_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_entity_record
    ON audit_logs(entity, record_id);

COMMIT;
