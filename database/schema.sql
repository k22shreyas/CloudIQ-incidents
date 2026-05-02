-- =============================================================
-- DROP TABLES (for clean re-initialization)
-- =============================================================
DROP TABLE IF EXISTS incident_services;
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS root_cause_categories;
DROP TABLE IF EXISTS services;
DROP TABLE IF EXISTS regions;
DROP TABLE IF EXISTS providers;

-- =============================================================
-- TABLE 1: providers
-- Stores unique cloud provider names.
-- Normalized to avoid repeating provider strings in incidents.
-- =============================================================
CREATE TABLE providers (
    provider_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,          -- e.g. "AWS", "GCP"
    headquarters  TEXT,                             -- company HQ country
    founded_year  INTEGER,
    created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- TABLE 2: regions
-- Stores geographic deployment regions (cloud zones).
-- =============================================================
CREATE TABLE regions (
    region_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,            -- e.g. "us-east-1"
    continent   TEXT,                               -- "North America", etc.
    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- TABLE 3: services
-- Stores service types and their subtypes.
-- One service can have multiple subtypes (e.g. Compute/Lambda).
-- =============================================================
CREATE TABLE services (
    service_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,                   -- "Compute", "Storage"
    subtype     TEXT,                               -- "Lambda", "S3", "RDS"
    UNIQUE (name, subtype)
);

-- =============================================================
-- TABLE 4: root_cause_categories
-- Lookup table for incident root cause types.
-- =============================================================
CREATE TABLE root_cause_categories (
    category_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,           -- "Hardware", "Software"
    description  TEXT
);

-- =============================================================
-- TABLE 5: incidents  (MAIN FACT TABLE)
-- Each row represents one cloud outage incident.
-- References providers, regions, services, root_cause_categories.
-- =============================================================
CREATE TABLE incidents (
    incident_id              TEXT    PRIMARY KEY,           -- UUID
    provider_id              INTEGER NOT NULL REFERENCES providers(provider_id),
    region_id                INTEGER NOT NULL REFERENCES regions(region_id),
    service_id               INTEGER NOT NULL REFERENCES services(service_id),
    category_id              INTEGER REFERENCES root_cause_categories(category_id),
    start_time               TEXT    NOT NULL,
    end_time                 TEXT,
    duration_minutes         INTEGER CHECK (duration_minutes >= 0),
    severity                 TEXT    NOT NULL CHECK (severity IN ('Low','Medium','High','Critical')),
    status                   TEXT    NOT NULL CHECK (status IN ('Resolved','Investigating','Monitoring')),
    root_cause_description   TEXT,
    customers_affected       INTEGER CHECK (customers_affected >= 0),
    revenue_loss_usd         REAL    CHECK (revenue_loss_usd >= 0),
    sla_violation            INTEGER DEFAULT 0 CHECK (sla_violation IN (0,1)),  -- boolean
    region_impact_score      REAL    CHECK (region_impact_score BETWEEN 0 AND 100),
    service_impact_score     REAL    CHECK (service_impact_score BETWEEN 0 AND 100),
    ticket_count             INTEGER DEFAULT 0,
    detection_method         TEXT,                          -- "Alert","Customer Report","Automated Monitoring"
    mitigation_action        TEXT,                          -- "Rollback","Patch","Restart","Scale Up"
    engineers_involved       INTEGER DEFAULT 1,
    engineer_response_time_minutes INTEGER,
    backup_triggered         INTEGER DEFAULT 0 CHECK (backup_triggered IN (0,1)),
    post_mortem_completed    INTEGER DEFAULT 0 CHECK (post_mortem_completed IN (0,1)),
    is_recurrent             INTEGER DEFAULT 0 CHECK (is_recurrent IN (0,1)),
    external_factors         TEXT,                          -- "DDoS","Weather","Vendor","None"
    scheduled_maintenance_conflict INTEGER DEFAULT 0,
    patch_applied            INTEGER DEFAULT 0,
    system_load_before       REAL,
    system_load_after        REAL,
    user_feedback_score      REAL CHECK (user_feedback_score BETWEEN 1 AND 5),
    notes                    TEXT,
    created_at               TEXT    DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- TABLE 6: incident_services  (MANY-TO-MANY JUNCTION)
-- An incident can affect multiple services beyond its primary
-- service (e.g. a network outage cascading into Storage + DB).
-- =============================================================
CREATE TABLE incident_services (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id  TEXT    NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    service_id   INTEGER NOT NULL REFERENCES services(service_id),
    impact_level TEXT    CHECK (impact_level IN ('Primary','Secondary','Tertiary')),
    UNIQUE (incident_id, service_id)
);

-- =============================================================
-- INDEXES for query performance
-- =============================================================
CREATE INDEX idx_incidents_provider  ON incidents(provider_id);
CREATE INDEX idx_incidents_region    ON incidents(region_id);
CREATE INDEX idx_incidents_severity  ON incidents(severity);
CREATE INDEX idx_incidents_status    ON incidents(status);
CREATE INDEX idx_incidents_start     ON incidents(start_time);
CREATE INDEX idx_inc_svc_incident    ON incident_services(incident_id);

-- =============================================================
-- SEED DATA: providers
-- =============================================================
INSERT INTO providers (name, headquarters, founded_year) VALUES
    ('AWS',        'United States', 2006),
    ('GCP',        'United States', 2008),
    ('Azure',      'United States', 2010),
    ('IBM',        'United States', 1911),
    ('Oracle',     'United States', 1977),
    ('Cloudflare', 'United States', 2009);

-- =============================================================
-- SEED DATA: regions
-- =============================================================
INSERT INTO regions (name, continent) VALUES
    ('us-east-1',       'North America'),
    ('us-east-2',       'North America'),
    ('us-west-1',       'North America'),
    ('us-west-2',       'North America'),
    ('eu-central-1',    'Europe'),
    ('eu-west-1',       'Europe'),
    ('europe-west2',    'Europe'),
    ('asia-southeast1', 'Asia'),
    ('ap-northeast-1',  'Asia'),
    ('ap-south-1',      'Asia'),
    ('sa-east-1',       'South America'),
    ('ca-central-1',    'North America');

-- =============================================================
-- SEED DATA: services
-- =============================================================
INSERT INTO services (name, subtype) VALUES
    ('Compute',    'EC2'),
    ('Compute',    'Lambda'),
    ('Compute',    'Cloud Functions'),
    ('Storage',    'S3'),
    ('Storage',    'Blob'),
    ('Storage',    'GCS'),
    ('Database',   'RDS'),
    ('Database',   'DynamoDB'),
    ('Database',   'BigQuery'),
    ('Database',   'Cloud SQL'),
    ('Networking', 'VPC'),
    ('Networking', 'CDN'),
    ('AI/ML',      'SageMaker'),
    ('AI/ML',      'Vertex AI'),
    ('AI/ML',      'Watson'),
    ('Monitoring', 'CloudWatch');

-- =============================================================
-- SEED DATA: root_cause_categories
-- =============================================================
INSERT INTO root_cause_categories (name, description) VALUES
    ('Hardware',    'Physical server, disk, or network hardware failure'),
    ('Software',    'Application bugs, OS crashes, or bad deployments'),
    ('Human Error', 'Misconfiguration, accidental deletion, or operational mistake'),
    ('Security',    'DDoS attacks, data breach, or unauthorized access'),
    ('Unknown',     'Root cause not yet determined'),
    ('Network',     'ISP issues, routing failures, or DNS problems');

-- =============================================================
-- SEED DATA: incidents
--
-- Incidents are loaded from CSV at database initialization time
-- by setup_db.py. Keep this section empty so the schema can be
-- recreated cleanly without hardcoded sample rows.
-- =============================================================

-- =============================================================
-- EXAMPLE CRUD QUERIES
-- =============================================================

-- --- INSERT a new incident ---
-- INSERT INTO incidents (
--     incident_id, provider_id, region_id, service_id, category_id,
--     start_time, end_time, duration_minutes, severity, status,
--     root_cause_description, customers_affected, revenue_loss_usd, sla_violation
-- ) VALUES (
--     'new-uuid-here', 1, 1, 2, 2,
--     '2026-04-10 08:00:00', '2026-04-10 10:00:00', 120,
--     'High', 'Resolved', 'Deployment config error.', 5000, 75000.00, 0
-- );

-- --- SELECT all incidents with joins ---
-- SELECT i.incident_id, p.name AS provider, r.name AS region,
--        s.name || '/' || COALESCE(s.subtype,'') AS service,
--        i.severity, i.status, i.duration_minutes,
--        i.customers_affected, i.revenue_loss_usd, c.name AS root_cause
-- FROM incidents i
-- JOIN providers p ON i.provider_id = p.provider_id
-- JOIN regions   r ON i.region_id   = r.region_id
-- JOIN services  s ON i.service_id  = s.service_id
-- LEFT JOIN root_cause_categories c ON i.category_id = c.category_id
-- ORDER BY i.start_time DESC;

-- --- UPDATE incident status ---
-- UPDATE incidents SET status = 'Resolved', end_time = CURRENT_TIMESTAMP
-- WHERE incident_id = 'some-uuid';

-- --- DELETE an incident ---
-- DELETE FROM incidents WHERE incident_id = 'some-uuid';


-- =============================================================
-- ANALYTICAL QUERIES
-- =============================================================

-- 1. Incidents by provider
-- SELECT p.name, COUNT(*) AS total
-- FROM incidents i JOIN providers p ON i.provider_id = p.provider_id
-- GROUP BY p.name ORDER BY total DESC;

-- 2. Total revenue loss by root cause
-- SELECT c.name, SUM(i.revenue_loss_usd) AS total_loss
-- FROM incidents i JOIN root_cause_categories c ON i.category_id = c.category_id
-- GROUP BY c.name ORDER BY total_loss DESC;

-- 3. Average duration by severity
-- SELECT severity, AVG(duration_minutes) AS avg_duration, COUNT(*) AS count
-- FROM incidents GROUP BY severity;

-- 4. Incidents by region
-- SELECT r.name, COUNT(*) AS total, SUM(customers_affected) AS customers
-- FROM incidents i JOIN regions r ON i.region_id = r.region_id
-- GROUP BY r.name ORDER BY total DESC;

-- 5. SLA violation rate by provider
-- SELECT p.name,
--        COUNT(*) AS total,
--        SUM(sla_violation) AS violations,
--        ROUND(100.0 * SUM(sla_violation) / COUNT(*), 1) AS violation_pct
-- FROM incidents i JOIN providers p ON i.provider_id = p.provider_id
-- GROUP BY p.name;
