# Cloud Infrastructure Incident Database & Visualization Platform

> Graduate Database Systems Course Project  
> Authors: **Disha Churi** (Database Design) · **Shreyas Karanam** (Backend / Flask) · **Linthoi Laishram** (Data Architecture)

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Initialize the database (creates cloud_incidents.db)
python setup_db.py

# 3. Run the Flask app
python app.py

# 4. Open in your browser
#    http://127.0.0.1:5000         — Incident table + CRUD
#    http://127.0.0.1:5000/analytics — Charts dashboard
```

---

## Project Structure

```
cloud_incident_db/
├── app.py                  ← Flask application (all routes)
├── setup_db.py             ← Database initialization script
├── requirements.txt        ← Python dependencies
├── cloud_incidents.db      ← SQLite database (auto-created)
│
├── database/
│   └── schema.sql          ← CREATE TABLE + seed data + queries
│
├── templates/
│   ├── index.html          ← Incident list, Add/Edit/Delete
│   └── analytics.html      ← Chart.js dashboard (7 charts)
│
└── static/
    └── style.css           ← Dark-theme custom styles
```

---

## Tech Stack

| Layer        | Technology                    |
|-------------|-------------------------------|
| Backend     | Python 3.10+ / Flask 3.x      |
| Database    | SQLite 3 (file: cloud_incidents.db) |
| Frontend    | HTML5, Bootstrap 5.3, Vanilla JS |
| Charts      | Chart.js 4.4                  |
| Icons       | Bootstrap Icons 1.11          |

**Why SQLite?** The dataset is a single-tenant academic project (~1,000 rows). SQLite requires zero server setup, the `.db` file ships alongside the code, and Flask can connect to it with the built-in `sqlite3` module — no ORM or driver installation needed.

---

## Database Design — Normalized to 3NF

### ER Diagram (Text)

```
┌─────────────┐         ┌─────────────────────┐         ┌──────────────┐
│  providers  │         │      incidents       │         │   regions    │
│─────────────│         │─────────────────────│         │──────────────│
│ PK provider_id│◄──────│ FK provider_id  (NN)│         │ PK region_id │
│    name (UQ)│         │ FK region_id    (NN)│────────►│    name (UQ) │
│ headquarters│         │ FK service_id   (NN)│         │    continent │
│ founded_year│         │ FK category_id      │         └──────────────┘
└─────────────┘         │ PK incident_id  (UQ)│
                        │    start_time   (NN)│         ┌──────────────┐
                        │    severity     (CK)│         │   services   │
                        │    status       (CK)│         │──────────────│
                        │    duration_min     │◄────────│ PK service_id│
                        │    customers_aff.   │         │    name  (NN)│
                        │    revenue_loss     │         │    subtype   │
                        │    sla_violation(CK)│         │ UQ(name,sub) │
                        │    ... 20+ fields   │         └──────────────┘
                        └──────────┬──────────┘
                                   │ 1
                                   │
                                   │ N
                        ┌──────────▼──────────┐     ┌────────────────────────┐
                        │  incident_services  │     │  root_cause_categories │
                        │ (junction table)    │     │────────────────────────│
                        │─────────────────────│     │ PK category_id         │
                        │ FK incident_id      │     │    name (UQ, NN)       │
                        │ FK service_id       │     │    description         │
                        │    impact_level(CK) │     └────────────────────────┘
                        │ UQ(inc_id, svc_id)  │
                        └─────────────────────┘
```

### Cardinality Summary

| Relationship                        | Cardinality |
|------------------------------------|-------------|
| Provider → Incidents               | 1 : N       |
| Region → Incidents                 | 1 : N       |
| Service → Incidents (primary)      | 1 : N       |
| Root Cause Category → Incidents    | 1 : N       |
| Incidents ↔ Services (via junction)| M : N       |

---

## Table Descriptions

### 1. `providers`
Stores unique cloud vendors. Normalized so the provider name is never repeated inline in incident rows — only a compact `provider_id` integer FK is stored.

| Column        | Type    | Constraints       |
|--------------|---------|-------------------|
| provider_id  | INTEGER | PK AUTOINCREMENT  |
| name         | TEXT    | NOT NULL, UNIQUE  |
| headquarters | TEXT    |                   |
| founded_year | INTEGER |                   |

### 2. `regions`
Geographic deployment zones. Separating regions into their own table removes the redundancy of storing "us-east-1" as a string on every incident row and makes region-level aggregation trivially indexed.

| Column    | Type    | Constraints       |
|----------|---------|-------------------|
| region_id | INTEGER | PK AUTOINCREMENT  |
| name      | TEXT    | NOT NULL, UNIQUE  |
| continent | TEXT    |                   |

### 3. `services`
Cloud service types (Compute, Storage …) together with their subtypes (Lambda, S3 …). The composite `UNIQUE(name, subtype)` prevents duplicates while allowing the same service name with different subtypes.

| Column     | Type    | Constraints              |
|-----------|---------|--------------------------|
| service_id | INTEGER | PK AUTOINCREMENT         |
| name       | TEXT    | NOT NULL                 |
| subtype    | TEXT    |                          |
| —          |         | UNIQUE (name, subtype)   |

### 4. `root_cause_categories`
Lookup table for the six root cause buckets (Hardware, Software, Human Error, Security, Network, Unknown). Normalized so incident rows carry only a `category_id` FK; renaming a category is a single-row UPDATE.

| Column      | Type    | Constraints       |
|------------|---------|-------------------|
| category_id | INTEGER | PK AUTOINCREMENT  |
| name        | TEXT    | NOT NULL, UNIQUE  |
| description | TEXT    |                   |

### 5. `incidents` ← Main fact table
One row per outage event. All measurable attributes (duration, revenue loss, SLA flag, engineer count, etc.) live here. Multi-valued service associations are offloaded to the junction table below.

Key columns and their constraints:

| Column              | Constraint                                           |
|---------------------|------------------------------------------------------|
| incident_id         | PRIMARY KEY (UUID string)                           |
| provider_id         | NOT NULL, FK → providers                            |
| region_id           | NOT NULL, FK → regions                              |
| service_id          | NOT NULL, FK → services                             |
| category_id         | FK → root_cause_categories (nullable)               |
| severity            | CHECK IN ('Low','Medium','High','Critical')          |
| status              | CHECK IN ('Resolved','Investigating','Monitoring')   |
| duration_minutes    | CHECK >= 0                                          |
| customers_affected  | CHECK >= 0                                          |
| revenue_loss_usd    | CHECK >= 0                                          |
| sla_violation       | CHECK IN (0,1) — boolean                            |
| region_impact_score | CHECK BETWEEN 0 AND 100                             |
| user_feedback_score | CHECK BETWEEN 1 AND 5                               |

### 6. `incident_services` — Junction table (M:N)
An outage can cascade across multiple services beyond its primary service (e.g. a network failure hitting both Storage and Compute). This table resolves the many-to-many relationship without repeating incident data.

| Column       | Constraint                                   |
|-------------|----------------------------------------------|
| incident_id  | NOT NULL, FK → incidents ON DELETE CASCADE   |
| service_id   | NOT NULL, FK → services                      |
| impact_level | CHECK IN ('Primary','Secondary','Tertiary')  |
| —            | UNIQUE (incident_id, service_id)             |

---

## Constraint Explanations

| Constraint  | Where used                    | Why                                                                 |
|------------|-------------------------------|---------------------------------------------------------------------|
| PRIMARY KEY | Every table                   | Uniquely identifies each row; enables FK references                 |
| NOT NULL    | All FK columns, name, start_time | Prevents orphaned or incomplete records                          |
| UNIQUE      | provider.name, region.name, etc. | Prevents accidental duplicates in lookup tables                 |
| UNIQUE composite | services(name, subtype)   | Same service type can have different subtypes; pair must be unique  |
| FOREIGN KEY | incidents → providers/regions/etc. | Enforces referential integrity; no dangling references         |
| CHECK       | severity, status, sla_violation, scores | Enforces domain validity at the database level            |
| ON DELETE CASCADE | incident_services → incidents | Deleting an incident auto-removes its service links         |

---

## CRUD Routes

| Method | URL                    | Operation        |
|--------|------------------------|------------------|
| GET    | `/`                    | List all incidents (with filters) |
| POST   | `/add`                 | Create new incident |
| GET    | `/incident/<id>`       | Read one (JSON, for edit modal) |
| POST   | `/update/<id>`         | Update incident  |
| POST   | `/delete/<id>`         | Delete incident  |
| GET    | `/analytics`           | Analytics page   |
| GET    | `/api/analytics`       | Analytics JSON (consumed by Chart.js) |

---

## Analytics Dashboard — 7 Charts

1. **Incidents by Provider** — Bar chart; which vendors have the most outages
2. **Incidents by Severity** — Doughnut; severity distribution
3. **Revenue Loss by Root Cause** — Horizontal bar; financial impact per failure category
4. **Incidents by Status** — Doughnut; how many are open vs resolved
5. **Avg Downtime by Severity** — Bar; Critical incidents last longer on average
6. **SLA Violation Rate by Provider** — Bar; accountability metric per vendor
7. **Customers Affected by Region** — Horizontal bar; geographic exposure

---

## Contribution Table

| Name           | Role              | Tasks                                               | Est. Hours |
|---------------|-------------------|-----------------------------------------------------|-----------|
| Disha Churi   | Database Design   | Schema (6 tables), constraints, seed data (30+ rows), analytical SQL queries, ER diagram | 12 |
| Shreyas Karanam | Backend & Frontend | Flask app, 7 routes, CRUD logic, HTML templates, Chart.js dashboard, CSS dark theme | 14 |

---

## AI Acknowledgement

> Portions of this project were generated using **Claude Sonnet** (Anthropic, April 2026) for code scaffolding, SQL query generation, and documentation drafting. All generated code was reviewed, corrected, and integrated by the project authors.
