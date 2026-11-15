-- ============================================================================
-- METLINK Seed Data (Part 1: Core Tables)
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Admins: Staff accounts
-- ----------------------------------------------------------------------------
INSERT INTO admins (admin_id, username, password_hash, full_name, email, role, is_active, created_at)
VALUES
    (1, 'aline.uwase',  '$2b$12$KIX9mP4tQv6eR8wL1zN3uO7yB5vC2xM0pA4sD6fG8hJ1kL3nQ5rT7', 'Aline Uwase',  'aline.uwase@metlink.rw',  'super_admin',    TRUE, '2026-10-01 08:30:00+02'),
    (2, 'eric.mugisha', '$2b$12$M9pL2kX8vN4qW6rT1yU3zI5oP7aS0dF2gH4jK6lZ8xC9vB1nM3qR5', 'Eric Mugisha', 'eric.mugisha@metlink.rw', 'market_analyst', TRUE, '2026-10-03 09:15:00+02')
ON CONFLICT (admin_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2. Farmers: Registered by admins in Kamonyi sectors
-- ----------------------------------------------------------------------------
INSERT INTO farmers (farmer_id, phone_number, name, location, preferred_language, registration_source, registered_by, is_active, registered_at)
VALUES
    (1,  '+250788419204', 'Jean Bosco Habimana',     'Runda',        'rw', 'admin', 1, TRUE,  '2026-10-05 10:12:00+02'),
    (2,  '+250783902145', 'Marie Claire Mukamana',   'Gacurabwenge', 'rw', 'admin', 1, TRUE,  '2026-10-06 11:40:00+02'),
    (3,  '+250728551902', 'Theogene Nshimiyimana',   'Rugalika',     'en', 'admin', 2, TRUE,  '2026-10-08 14:05:00+02'),
    (4,  '+250785110489', 'Vestine Ingabire',        'Kayenzi',      'rw', 'admin', 2, TRUE,  '2026-10-10 09:50:00+02'),
    (5,  '+250732674019', 'Emmanuel Bizimana',       'Kayumbu',      'en', 'admin', 1, TRUE,  '2026-10-12 16:20:00+02'),
    (6,  '+250789304812', 'Claudine Uwimana',        'Mugina',       'rw', 'admin', 1, TRUE,  '2026-10-15 08:45:00+02'),
    (7,  '+250784729103', 'Pacifique Ndayisaba',     'Nyamiyaga',    'en', 'admin', 2, TRUE,  '2026-10-18 13:10:00+02'),
    (8,  '+250725883410', 'Solange Nyirahabimana',   'Musambira',    'rw', 'admin', 2, TRUE,  '2026-10-21 15:30:00+02'),
    (9,  '+250787194520', 'Innocent Tuyisenge',      'Ngamba',       'en', 'admin', 1, TRUE,  '2026-10-25 10:00:00+02'),
    (10, '+250781449032', 'Beatrice Mukandayisenga', 'Karama',       'rw', 'admin', 2, FALSE, '2026-10-28 12:15:00+02')
ON CONFLICT (farmer_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 3. Harvest Submissions: Expected tomato harvests sent via USSD
-- ----------------------------------------------------------------------------
INSERT INTO harvest_submissions (
    submission_id, farmer_id, expected_harvest_date, quantity_kg,
    tomato_maturity, has_suitable_preservation, location, status, created_at
)
VALUES
    (1, 1, DATE '2026-11-16', 450.00,  'RIPE',    FALSE, 'Runda',        'PROCESSED', '2026-11-10 07:45:00+02'),
    (2, 1, DATE '2026-11-24', 620.50,  'GREEN',   TRUE,  'Runda',        'PROCESSED', '2026-11-11 09:20:00+02'),
    (3, 2, DATE '2026-11-18', 800.00,  'TURNING', TRUE,  'Gacurabwenge', 'PROCESSED', '2026-11-11 14:10:00+02'),
    (4, 3, DATE '2026-11-19', 1250.75, 'RIPE',    FALSE, 'Rugalika',     'PROCESSED', '2026-11-12 08:55:00+02'),
    (5, 4, DATE '2026-11-22', 310.00,  'GREEN',   FALSE, 'Kayenzi',      'PENDING',   '2026-11-13 11:30:00+02'),
    (6, 5, DATE '2026-11-25', 540.25,  'TURNING', TRUE,  'Kayumbu',      'PENDING',   '2026-11-13 16:05:00+02'),
    (7, 6, DATE '2026-11-15', 200.00,  'RIPE',    FALSE, 'Mugina',       'CANCELLED', '2026-11-14 09:10:00+02'),
    (8, 7, DATE '2026-11-21', 950.00,  'TURNING', FALSE, 'Nyamiyaga',    'PROCESSED', '2026-11-14 13:40:00+02')
ON CONFLICT (submission_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 4. Seasonal Information: Only Season A 2027 is currently active
-- ----------------------------------------------------------------------------
INSERT INTO seasonal_information (
    season_id, season_name, start_date, end_date, description, is_active, created_by, created_at
)
VALUES
    (1, 'Season B 2026', DATE '2026-02-01', DATE '2026-05-31', 'Main rainy season with heavy rainfall across Kamonyi.', FALSE, 1, '2026-10-02 10:00:00+02'),
    (2, 'Season C 2026', DATE '2026-06-01', DATE '2026-08-31', 'Dry season relying on marshland irrigation.',          FALSE, 2, '2026-10-02 10:15:00+02'),
    (3, 'Season A 2027', DATE '2026-09-01', DATE '2027-01-31', 'Short rains planting and primary harvest season.',    TRUE,  1, '2026-10-02 10:30:00+02')
ON CONFLICT (season_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 5. Market Information: Current Rwandan tomato prices (RWF per kg)
-- ----------------------------------------------------------------------------
INSERT INTO market_information (
    market_id, market_name, location, average_price_per_kg, demand_level, source, is_active, created_by, created_at
)
VALUES
    (1, 'Kimironko Market',    'Gasabo',     620.00, 'HIGH',   'Field Survey',   TRUE, 1, '2026-11-12 08:30:00+02'),
    (2, 'Nyabugogo Market',    'Nyarugenge', 510.00, 'MEDIUM', 'Field Survey',   TRUE, 1, '2026-11-12 09:45:00+02'),
    (3, 'Kicukiro Market',     'Kicukiro',   700.00, 'HIGH',   'Wholesale Desk', TRUE, 2, '2026-11-13 08:15:00+02'),
    (4, 'Nyamirambo Market',   'Nyarugenge', 410.00, 'LOW',    'Field Survey',   TRUE, 2, '2026-11-13 10:20:00+02'),
    (5, 'Remera Market',       'Gasabo',     540.00, 'MEDIUM', 'Field Survey',   TRUE, 1, '2026-11-14 08:50:00+02'),
    (6, 'Nyabugogo Wholesale', 'Nyarugenge', 680.00, 'HIGH',   'Wholesale Desk', TRUE, 2, '2026-11-14 10:05:00+02')
ON CONFLICT (market_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 6. Audit Logs: Realistic staff activity history
-- ----------------------------------------------------------------------------
INSERT INTO audit_logs (
    log_id, admin_id, action, entity, record_id, old_value, new_value, details, created_at
)
VALUES
    (1, 1, 'CREATE', 'farmers', 1, NULL,
        '{"name": "Jean Bosco Habimana", "location": "Runda"}',
        'Registered farmer Jean Bosco Habimana from Runda sector.',
        '2026-10-05 10:12:05+02'),
    (2, 2, 'UPDATE', 'farmers', 10,
        '{"is_active": true}', '{"is_active": false}',
        'Deactivated Beatrice Mukandayisenga account due to inactive phone number.',
        '2026-11-08 14:22:00+02'),
    (3, 1, 'CREATE', 'market_information', 1, NULL,
        '{"market_name": "Kimironko Market", "average_price_per_kg": 620.00}',
        'Added daily tomato price for Kimironko Market at 620 RWF/kg.',
        '2026-11-12 08:30:10+02'),
    (4, 2, 'CREATE', 'market_information', 6, NULL,
        '{"market_name": "Nyabugogo Wholesale", "average_price_per_kg": 680.00}',
        'Logged wholesale tomato price for Nyabugogo Wholesale at 680 RWF/kg.',
        '2026-11-14 10:05:12+02')
ON CONFLICT (log_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 7. Decision Rules: Practical rules accounting for ripeness, storage & volume
-- ----------------------------------------------------------------------------
INSERT INTO decision_rules (
    rule_id, rule_name, maturity, price_trend, demand_level,
    preservation_required, action, waiting_period_days, min_quantity_kg, priority, is_active
)
VALUES
    (1, 'Ripe Immediate Local Sale',           'RIPE',    'STABLE',  'HIGH',   FALSE, 'SELL_NOW',                NULL, NULL,   1, TRUE),
    (2, 'Green Storage for Price Rise',        'GREEN',   'RISING',  'MEDIUM', TRUE,  'STORE_AND_WAIT',          7,    200.00, 2, TRUE),
    (3, 'Turning Short Hold for Better Price', 'TURNING', 'RISING',  'HIGH',   TRUE,  'STORE_AND_WAIT',          4,    250.00, 3, TRUE),
    (4, 'Ripe Bulk Transport to Kigali',       'RIPE',    'FALLING', 'LOW',    FALSE, 'SEEK_ALTERNATIVE_MARKET', NULL, 400.00, 1, TRUE),
    (5, 'Turning Quick Sale No Storage',       'TURNING', 'FALLING', 'MEDIUM', FALSE, 'SELL_NOW',                NULL, NULL,   4, TRUE)
ON CONFLICT (rule_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 8. Recommendations: Advice sent for processed harvest submissions
-- ----------------------------------------------------------------------------
INSERT INTO recommendations (
    recommendation_id, submission_id, decision_rule_id, action,
    reason, waiting_period_days, confidence_level, created_at
)
VALUES
    (1, 1, 1, 'SELL_NOW',
        'Your tomatoes are ripe and you have no cold storage. Sell today at Kimironko Market where demand is high (620 RWF/kg).',
        NULL, 'HIGH', '2026-11-10 07:46:00+02'),
    (2, 2, 2, 'STORE_AND_WAIT',
        'Your 620.5 kg of green tomatoes can be stored safely for 7 days while wholesale prices continue rising.',
        7, 'HIGH', '2026-11-11 09:21:00+02'),
    (3, 3, 3, 'STORE_AND_WAIT',
        'Hold your turning tomatoes in cool storage for 4 days to catch peak weekend demand at Kicukiro Market.',
        4, 'MEDIUM', '2026-11-11 14:12:00+02'),
    (4, 4, 4, 'SEEK_ALTERNATIVE_MARKET',
        'Local demand is low, and your 1,250.75 kg harvest justifies transport to Nyabugogo Wholesale (680 RWF/kg).',
        NULL, 'HIGH', '2026-11-12 08:57:00+02'),
    (5, 8, 5, 'SELL_NOW',
        'Without suitable preservation for 950 kg of turning tomatoes, sell immediately at Remera Market (540 RWF/kg).',
        NULL, 'MEDIUM', '2026-11-14 13:42:00+02')
ON CONFLICT (recommendation_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 9. Recommendation Evidence: Point-in-time market, season & rule snapshots
-- ----------------------------------------------------------------------------
INSERT INTO recommendation_evidence (
    evidence_id, recommendation_id, evidence_type,
    market_information_id, seasonal_information_id, decision_rule_id,
    snapshot, notes, created_at
)
VALUES
    (1, 1, 'MARKET', 1, NULL, NULL,
        '{"market_name": "Kimironko Market", "average_price_per_kg": 620.00, "demand_level": "HIGH"}',
        'Kimironko Market price recorded at time of submission.', '2026-11-10 07:46:00+02'),
    (2, 1, 'RULE', NULL, NULL, 1,
        '{"rule_name": "Ripe Immediate Local Sale", "action": "SELL_NOW"}',
        'Matched ripe tomato immediate sale rule.', '2026-11-10 07:46:00+02'),
    (3, 2, 'SEASONAL', NULL, 3, NULL,
        '{"season_name": "Season A 2027", "description": "Short rains planting and primary harvest season."}',
        'Evaluated under active Season A 2027 weather conditions.', '2026-11-11 09:21:00+02'),
    (4, 4, 'MARKET', 6, NULL, NULL,
        '{"market_name": "Nyabugogo Wholesale", "average_price_per_kg": 680.00, "demand_level": "HIGH"}',
        'Recommended Nyabugogo Wholesale due to higher bulk price.', '2026-11-12 08:57:00+02')
ON CONFLICT (evidence_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 10. SMS Logs: SMS notifications dispatched to farmers
-- ----------------------------------------------------------------------------
INSERT INTO sms_logs (
    sms_id, recommendation_id, phone_number, message, status, provider_id, sent_at, delivered_at
)
VALUES
    (1, 1, '+250788419204',
        'METLINK: Inyanya zawe zireze. Zigurishe uyu munsi ku isoko rya Kimironko (620 RWF/kg) kuko zikenewe cyane.',
        'DELIVERED', 'ATXid_90182a4f1c', '2026-11-10 07:46:05+02', '2026-11-10 07:46:14+02'),
    (2, 2, '+250788419204',
        'METLINK: Bika inyanya zawe mbisi ahantu hafutse iminsi 7. Ibiciro biri kuzamuka ku isoko.',
        'DELIVERED', 'ATXid_90182b7e2d', '2026-11-11 09:21:04+02', '2026-11-11 09:21:11+02'),
    (3, 3, '+250783902145',
        'METLINK: Tegereza iminsi 4 mbere yo kugurisha inyanya zawe kugira ngo ubone igiciro cyiza i Kicukiro.',
        'SENT', 'ATXid_90182c9a3e', '2026-11-11 14:12:03+02', NULL),
    (4, 4, '+250728551902',
        'METLINK: Local demand is low. Take your 1,250 kg harvest to Nyabugogo Wholesale for 680 RWF/kg.',
        'DELIVERED', 'ATXid_90182d1b4f', '2026-11-12 08:57:06+02', '2026-11-12 08:57:18+02'),
    (5, 5, '+250784729103',
        'METLINK: No cold storage reported for your 950 kg harvest. Sell immediately at Remera Market (540 RWF/kg).',
        'FAILED', NULL, '2026-11-14 13:42:05+02', NULL)
ON CONFLICT (sms_id) DO NOTHING;

-- Reset ID sequences so new records created in the admin dashboard never clash
SELECT setval(pg_get_serial_sequence('admins', 'admin_id'),               COALESCE(MAX(admin_id), 1))      FROM admins;
SELECT setval(pg_get_serial_sequence('farmers', 'farmer_id'),             COALESCE(MAX(farmer_id), 1))     FROM farmers;
SELECT setval(pg_get_serial_sequence('harvest_submissions', 'submission_id'), COALESCE(MAX(submission_id), 1)) FROM harvest_submissions;
SELECT setval(pg_get_serial_sequence('seasonal_information', 'season_id'), COALESCE(MAX(season_id), 1))    FROM seasonal_information;
SELECT setval(pg_get_serial_sequence('market_information', 'market_id'),  COALESCE(MAX(market_id), 1))     FROM market_information;
SELECT setval(pg_get_serial_sequence('audit_logs', 'log_id'),             COALESCE(MAX(log_id), 1))        FROM audit_logs;
SELECT setval(pg_get_serial_sequence('decision_rules', 'rule_id'),               COALESCE(MAX(rule_id), 1))           FROM decision_rules;
SELECT setval(pg_get_serial_sequence('recommendations', 'recommendation_id'),    COALESCE(MAX(recommendation_id), 1)) FROM recommendations;
SELECT setval(pg_get_serial_sequence('recommendation_evidence', 'evidence_id'),  COALESCE(MAX(evidence_id), 1))       FROM recommendation_evidence;
SELECT setval(pg_get_serial_sequence('sms_logs', 'sms_id'),                      COALESCE(MAX(sms_id), 1))            FROM sms_logs;

COMMIT;