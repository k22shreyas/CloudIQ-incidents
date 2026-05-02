"""
reweight_data.py
Replaces the uniformly-random synthetic data with realistic,
correlated distributions that actually tell a story in the charts.

Run:  python reweight_data.py
"""

import sqlite3, random, math, os
from datetime import datetime, timedelta

random.seed(42)
DB_PATH = os.path.join(os.path.dirname(__file__), "cloud_incidents.db")

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def gauss_int(mu, sigma, lo, hi):
    return int(clamp(round(random.gauss(mu, sigma)), lo, hi))

def gauss_float(mu, sigma, lo, hi, dp=1):
    return round(clamp(random.gauss(mu, sigma), lo, hi), dp)

def lognorm_int(mu_log, sigma_log, lo, hi):
    """Log-normal sample — good for skewed quantities like revenue / duration."""
    v = math.exp(random.gauss(mu_log, sigma_log))
    return int(clamp(round(v), lo, hi))

def weighted_choice(choices, weights):
    total = sum(weights)
    r = random.uniform(0, total)
    acc = 0
    for c, w in zip(choices, weights):
        acc += w
        if r <= acc:
            return c
    return choices[-1]

# ─────────────────────────────────────────────────────────────
# Distribution tables  (all correlated with severity)
# ─────────────────────────────────────────────────────────────

# 1. Severity  — heavy tail: most incidents are Low/Medium
SEV_CHOICES  = ['Critical', 'High',  'Medium', 'Low']
SEV_WEIGHTS  = [   6,         17,      37,       40  ]   # %

# 2. Provider  — realistic cloud market share
#    provider_id: AWS=1, GCP=2, Azure=3, IBM=4, Oracle=5, Cloudflare=6
PROVIDER_CHOICES = [1,   2,   3,   4,  5,  6 ]
PROVIDER_WEIGHTS = [33,  22,  27,  6,  9,  3 ]

# 3. Root-cause category
#    id:           SW=2  HW=1  Net=6  HumE=3  Sec=4  Unk=5
CAT_CHOICES = [2,   1,   6,   3,   4,   5 ]
CAT_WEIGHTS = [30,  20,  18,  15,  10,  7 ]

# 4. Status  — by severity
STATUS_BY_SEV = {
    'Critical': (['Resolved','Investigating','Monitoring'], [55, 28, 17]),
    'High':     (['Resolved','Investigating','Monitoring'], [68, 18, 14]),
    'Medium':   (['Resolved','Investigating','Monitoring'], [80,  9, 11]),
    'Low':      (['Resolved','Investigating','Monitoring'], [90,  4,  6]),
}

# 5. Duration (minutes) — log-normal params (mu, sigma of log)
#    Critical ≈ 12 h  |  High ≈ 5 h  |  Medium ≈ 90 min  |  Low ≈ 20 min
DURATION_PARAMS = {
    'Critical': (6.7,  0.5,   60,  4320),  # mu_log≈720 min
    'High':     (5.7,  0.5,   30,  1440),  # mu_log≈300 min
    'Medium':   (4.5,  0.5,   10,   480),  # mu_log≈90 min
    'Low':      (3.0,  0.5,    5,   180),  # mu_log≈20 min
}

# 6. Customers affected — log-normal
CUSTOMERS_PARAMS = {
    'Critical': (12.5, 0.8,  10_000,  5_000_000),
    'High':     (10.8, 0.7,   1_000,    500_000),
    'Medium':   ( 8.5, 0.7,     100,     50_000),
    'Low':      ( 6.0, 0.7,       5,      5_000),
}

# 7. Revenue loss (USD) — log-normal
REVENUE_PARAMS = {
    'Critical': (13.5, 0.7,  200_000,  8_000_000),
    'High':     (11.5, 0.7,   20_000,    800_000),
    'Medium':   ( 9.2, 0.7,    1_000,     80_000),
    'Low':      ( 7.0, 0.7,       50,      8_000),
}

# 8. SLA violation base probability per provider, then amplified by severity
SLA_BASE = {1: 0.20, 2: 0.24, 3: 0.28, 4: 0.40, 5: 0.44, 6: 0.32}  # AWS…CF
SLA_SEV_MULT = {'Critical': 2.5, 'High': 1.6, 'Medium': 0.8, 'Low': 0.3}

# 9. Engineers involved
ENG_PARAMS = {
    'Critical': (10, 3,  5, 25),
    'High':     ( 5, 2,  3, 12),
    'Medium':   ( 2, 1,  1,  6),
    'Low':      ( 1, 0,  1,  3),
}

# 10. Engineer response time (minutes)
RESP_PARAMS = {
    'Critical': ( 5, 3,   1,  15),
    'High':     (18, 8,   5,  40),
    'Medium':   (40, 15, 15,  90),
    'Low':      (75, 25, 30, 180),
}

# 11. Impact scores
REGION_IMPACT_PARAMS = {
    'Critical': (82, 10, 55, 100),
    'High':     (60, 12, 35,  90),
    'Medium':   (38, 12, 15,  65),
    'Low':      (15,  8,  2,  40),
}
SERVICE_IMPACT_PARAMS = {
    'Critical': (85, 10, 60, 100),
    'High':     (65, 12, 40,  90),
    'Medium':   (40, 12, 18,  70),
    'Low':      (18,  8,  3,  45),
}

# 12. Ticket count
TICKET_PARAMS = {
    'Critical': (600, 200, 100, 2000),
    'High':     (150,  60,  20,  600),
    'Medium':   ( 35,  15,   5,  150),
    'Low':      (  8,   4,   1,   40),
}

# 13. System load before (%)
LOAD_BEFORE_PARAMS = {
    'Critical': (82, 10, 55, 100),
    'High':     (68, 10, 45,  95),
    'Medium':   (55, 12, 30,  85),
    'Low':      (40, 12, 15,  70),
}

# 14. User feedback score (1–5, inverted: worse for critical)
FEEDBACK_PARAMS = {
    'Critical': (1.8, 0.5, 1.0, 3.0),
    'High':     (2.5, 0.6, 1.0, 3.8),
    'Medium':   (3.5, 0.6, 2.0, 5.0),
    'Low':      (4.3, 0.5, 3.0, 5.0),
}

# 15. Backup triggered probability
BACKUP_PROB = {'Critical': 0.72, 'High': 0.42, 'Medium': 0.16, 'Low': 0.04}

# 16. Post-mortem completed probability
PM_PROB = {'Critical': 0.95, 'High': 0.78, 'Medium': 0.44, 'Low': 0.14}

# 17. Is recurrent
RECURRENT_PROB = {'Critical': 0.14, 'High': 0.20, 'Medium': 0.26, 'Low': 0.28}

# 18. Detection method
DETECT_BY_SEV = {
    'Critical': (['Automated Monitoring','Alert','Customer Report'], [65, 32,  3]),
    'High':     (['Automated Monitoring','Alert','Customer Report'], [58, 35,  7]),
    'Medium':   (['Automated Monitoring','Alert','Customer Report'], [50, 35, 15]),
    'Low':      (['Automated Monitoring','Alert','Customer Report'], [35, 35, 30]),
}

# 19. Mitigation action
MITIGATION_BY_SEV = {
    'Critical': (['Rollback','Restart','Patch','Scale Up'], [40, 30, 20, 10]),
    'High':     (['Rollback','Restart','Patch','Scale Up'], [32, 28, 25, 15]),
    'Medium':   (['Rollback','Restart','Patch','Scale Up'], [25, 25, 32, 18]),
    'Low':      (['Rollback','Restart','Patch','Scale Up'], [20, 22, 38, 20]),
}

# 20. External factors
EXTERNAL_CHOICES = ['None', 'DDoS', 'Vendor', 'Weather']
EXTERNAL_WEIGHTS = [  63,     13,     13,       11     ]

# ─────────────────────────────────────────────────────────────
# Build a realistic row dict for one incident
# ─────────────────────────────────────────────────────────────

def build_row(incident_id):
    sev = weighted_choice(SEV_CHOICES, SEV_WEIGHTS)
    pid = weighted_choice(PROVIDER_CHOICES, PROVIDER_WEIGHTS)

    # Duration
    dur_p = DURATION_PARAMS[sev]
    dur   = lognorm_int(dur_p[0], dur_p[1], dur_p[2], dur_p[3])

    # Status — critical stays unresolved more
    sc, sw = STATUS_BY_SEV[sev]
    status = weighted_choice(sc, sw)

    # Start/end times — spread over 2 years
    base      = datetime(2022, 1, 1)
    start_off = random.randint(0, 730 * 24 * 60)
    start     = base + timedelta(minutes=start_off)
    end       = start + timedelta(minutes=dur) if status == 'Resolved' else None

    # Numeric columns
    cust_p   = CUSTOMERS_PARAMS[sev]
    rev_p    = REVENUE_PARAMS[sev]
    cust     = lognorm_int(cust_p[0], cust_p[1], cust_p[2], cust_p[3])
    revenue  = round(lognorm_int(rev_p[0], rev_p[1], rev_p[2], rev_p[3]) * random.uniform(0.85, 1.15), 2)

    # SLA violation
    sla_p    = clamp(SLA_BASE[pid] * SLA_SEV_MULT[sev], 0, 1)
    sla      = 1 if random.random() < sla_p else 0

    # Scores
    ri_p     = REGION_IMPACT_PARAMS[sev]
    si_p     = SERVICE_IMPACT_PARAMS[sev]
    r_imp    = gauss_float(ri_p[0], ri_p[1], ri_p[2], ri_p[3])
    s_imp    = gauss_float(si_p[0], si_p[1], si_p[2], si_p[3])

    # Engineers
    eng_p    = ENG_PARAMS[sev]
    eng      = gauss_int(eng_p[0], eng_p[1], eng_p[2], eng_p[3])

    # Response time
    resp_p   = RESP_PARAMS[sev]
    resp     = gauss_int(resp_p[0], resp_p[1], resp_p[2], resp_p[3])

    # Tickets
    tick_p   = TICKET_PARAMS[sev]
    tickets  = gauss_int(tick_p[0], tick_p[1], tick_p[2], tick_p[3])

    # System load
    lb_p     = LOAD_BEFORE_PARAMS[sev]
    load_b   = gauss_float(lb_p[0], lb_p[1], lb_p[2], lb_p[3])
    load_a   = round(clamp(load_b * random.uniform(0.25, 0.65), 5, load_b - 5), 1)

    # Feedback
    fb_p     = FEEDBACK_PARAMS[sev]
    feedback = gauss_float(fb_p[0], fb_p[1], fb_p[2], fb_p[3])

    # Booleans
    backup   = 1 if random.random() < BACKUP_PROB[sev] else 0
    pm       = 1 if random.random() < PM_PROB[sev]     else 0
    recur    = 1 if random.random() < RECURRENT_PROB[sev] else 0

    # Categoricals
    cat_id   = weighted_choice(CAT_CHOICES, CAT_WEIGHTS)
    detect   = weighted_choice(*zip(*zip(DETECT_BY_SEV[sev][0], DETECT_BY_SEV[sev][1])))
    detect   = weighted_choice(DETECT_BY_SEV[sev][0], DETECT_BY_SEV[sev][1])
    mitigate = weighted_choice(MITIGATION_BY_SEV[sev][0], MITIGATION_BY_SEV[sev][1])
    ext      = weighted_choice(EXTERNAL_CHOICES, EXTERNAL_WEIGHTS)

    return (
        pid,
        cat_id,
        start.strftime('%Y-%m-%d %H:%M:%S'),
        end.strftime('%Y-%m-%d %H:%M:%S') if end else None,
        dur,
        sev,
        status,
        cust,
        revenue,
        sla,
        r_imp,
        s_imp,
        tickets,
        detect,
        mitigate,
        eng,
        resp,
        backup,
        pm,
        recur,
        ext,
        feedback,
        load_b,
        load_a,
        incident_id,
    )

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")

print("Fetching incident IDs…")
ids = [r[0] for r in conn.execute("SELECT incident_id FROM incidents").fetchall()]
print(f"  {len(ids):,} rows found")

print("Generating realistic values…")
rows = [build_row(iid) for iid in ids]

print("Writing to database…")
conn.executemany("""
    UPDATE incidents SET
        provider_id                    = ?,
        category_id                    = ?,
        start_time                     = ?,
        end_time                       = ?,
        duration_minutes               = ?,
        severity                       = ?,
        status                         = ?,
        customers_affected             = ?,
        revenue_loss_usd               = ?,
        sla_violation                  = ?,
        region_impact_score            = ?,
        service_impact_score           = ?,
        ticket_count                   = ?,
        detection_method               = ?,
        mitigation_action              = ?,
        engineers_involved             = ?,
        engineer_response_time_minutes = ?,
        backup_triggered               = ?,
        post_mortem_completed          = ?,
        is_recurrent                   = ?,
        external_factors               = ?,
        user_feedback_score            = ?,
        system_load_before             = ?,
        system_load_after              = ?
    WHERE incident_id = ?
""", rows)
conn.commit()

# ─────────────────────────────────────────────────────────────
# Verification
# ─────────────────────────────────────────────────────────────
print("\n── Results ────────────────────────────────────────────")

checks = {
    "Severity split": """
        SELECT severity, COUNT(*) AS n,
               ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(),1) AS pct
        FROM incidents GROUP BY severity ORDER BY n DESC""",
    "Provider split": """
        SELECT p.name, COUNT(*) AS n,
               ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(),1) AS pct
        FROM incidents i JOIN providers p ON i.provider_id=p.provider_id
        GROUP BY p.name ORDER BY n DESC""",
    "Status split": """
        SELECT status, COUNT(*) AS n,
               ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(),1) AS pct
        FROM incidents GROUP BY status ORDER BY n DESC""",
    "Avg duration (min) by severity": """
        SELECT severity, ROUND(AVG(duration_minutes)) AS avg_min
        FROM incidents GROUP BY severity ORDER BY avg_min DESC""",
    "SLA violation % by provider": """
        SELECT p.name, ROUND(100.0*SUM(i.sla_violation)/COUNT(*),1) AS pct
        FROM incidents i JOIN providers p ON i.provider_id=p.provider_id
        GROUP BY p.name ORDER BY pct DESC""",
    "Revenue loss $M by root cause": """
        SELECT c.name, ROUND(SUM(i.revenue_loss_usd)/1e6,0) AS m
        FROM incidents i JOIN root_cause_categories c ON i.category_id=c.category_id
        GROUP BY c.name ORDER BY m DESC""",
    "Avg customers affected by severity": """
        SELECT severity, ROUND(AVG(customers_affected)) AS avg_cust
        FROM incidents GROUP BY severity ORDER BY avg_cust DESC""",
}

for label, q in checks.items():
    print(f"\n{label}:")
    for r in conn.execute(q).fetchall():
        print("  ", r)

conn.close()
print("\nDone.")
