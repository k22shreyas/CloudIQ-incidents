"""
app.py — Cloud Infrastructure Incident Database & Visualization Platform
Author  : Disha Churi & Shreyas Karanam
Backend : Python Flask + SQLite3
"""

import sqlite3
import uuid
import os
from datetime import datetime
from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, flash)

# ─────────────────────────────────────────────────────────────
# App configuration
# ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "cloud_incidents_secret_2024"

PER_PAGE = 50
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "cloud_incidents.db")
SQL_PATH = os.path.join(BASE_DIR, "database", "schema.sql")


# ─────────────────────────────────────────────────────────────
# Database helpers
# ─────────────────────────────────────────────────────────────
def get_db():
    """Return an open SQLite connection with Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Run schema.sql to (re-)create and seed the database."""
    with open(SQL_PATH, "r") as f:
        sql = f.read()
    conn = get_db()
    conn.executescript(sql)
    conn.commit()
    conn.close()
    print("[✓] Database initialized from schema.sql")


def query_db(sql, args=(), one=False):
    """Execute a SELECT and return Row(s)."""
    conn = get_db()
    cur  = conn.execute(sql, args)
    rows = cur.fetchall()
    conn.close()
    return (rows[0] if rows else None) if one else rows


def execute_db(sql, args=()):
    """Execute a write statement (INSERT / UPDATE / DELETE)."""
    conn = get_db()
    conn.execute(sql, args)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────
# Shared SELECT — incidents with all joined lookup names
# ─────────────────────────────────────────────────────────────
INCIDENTS_JOIN = """
    SELECT
        i.incident_id,
        p.name          AS provider,
        r.name          AS region,
        s.name          AS service,
        s.subtype       AS subtype,
        c.name          AS root_cause,
        i.start_time,
        i.end_time,
        i.duration_minutes,
        i.severity,
        i.status,
        i.root_cause_description,
        i.customers_affected,
        i.revenue_loss_usd,
        i.sla_violation,
        i.region_impact_score,
        i.service_impact_score,
        i.ticket_count,
        i.detection_method,
        i.mitigation_action,
        i.engineers_involved,
        i.engineer_response_time_minutes,
        i.backup_triggered,
        i.post_mortem_completed,
        i.is_recurrent,
        i.external_factors,
        i.user_feedback_score,
        i.system_load_before,
        i.system_load_after,
        i.notes,
        i.provider_id,
        i.region_id,
        i.service_id,
        i.category_id
    FROM incidents i
    JOIN providers             p ON i.provider_id = p.provider_id
    JOIN regions               r ON i.region_id   = r.region_id
    JOIN services              s ON i.service_id  = s.service_id
    LEFT JOIN root_cause_categories c ON i.category_id = c.category_id
"""


# ─────────────────────────────────────────────────────────────
# Lookup helpers for form dropdowns
# ─────────────────────────────────────────────────────────────
def rows_to_dict(rows):
    return [dict(r) for r in rows]


def get_providers():
    return rows_to_dict(query_db("SELECT provider_id, name FROM providers ORDER BY name"))

def get_regions():
    return rows_to_dict(query_db("SELECT region_id, name FROM regions ORDER BY name"))

def get_services():
    return rows_to_dict(query_db("SELECT service_id, name, subtype FROM services ORDER BY name, subtype"))

def get_categories():
    return rows_to_dict(query_db("SELECT category_id, name FROM root_cause_categories ORDER BY name"))


# ═════════════════════════════════════════════════════════════
# ROUTES
# ═════════════════════════════════════════════════════════════

# ── READ: list all incidents ─────────────────────────────────
@app.route("/")
def index():
    search    = request.args.get("search", "").strip()
    severity  = request.args.get("severity", "")
    status    = request.args.get("status", "")
    provider  = request.args.get("provider", "")

    try:
        page = max(1, int(request.args.get("page", 1) or 1))
    except (ValueError, TypeError):
        page = 1

    # Build shared WHERE clause
    where_sql = " WHERE 1=1"
    params    = []
    if search:
        where_sql += """ AND (p.name LIKE ? OR r.name LIKE ? OR s.name LIKE ?
                              OR i.root_cause_description LIKE ?)"""
        like = f"%{search}%"
        params += [like, like, like, like]
    if severity:
        where_sql += " AND i.severity = ?"
        params.append(severity)
    if status:
        where_sql += " AND i.status = ?"
        params.append(status)
    if provider:
        where_sql += " AND p.name = ?"
        params.append(provider)

    # Total matching count
    count_sql = (
        "SELECT COUNT(*) FROM incidents i"
        " JOIN providers p ON i.provider_id = p.provider_id"
        " JOIN regions r ON i.region_id = r.region_id"
        " JOIN services s ON i.service_id = s.service_id"
        " LEFT JOIN root_cause_categories c ON i.category_id = c.category_id"
        + where_sql
    )
    total_count = query_db(count_sql, params, one=True)[0]
    total_pages = max(1, (total_count + PER_PAGE - 1) // PER_PAGE)
    page        = min(page, total_pages)

    # Paginated incidents
    incidents = query_db(
        INCIDENTS_JOIN + where_sql + " ORDER BY i.start_time DESC LIMIT ? OFFSET ?",
        params + [PER_PAGE, (page - 1) * PER_PAGE]
    )

    # Summary KPIs (always global)
    kpis = query_db("""
        SELECT COUNT(*)                          AS total,
               SUM(revenue_loss_usd)             AS total_loss,
               SUM(customers_affected)           AS total_customers,
               ROUND(AVG(duration_minutes), 1)   AS avg_duration
        FROM incidents
    """, one=True)

    return render_template("index.html",
                           incidents=incidents,
                           providers=get_providers(),
                           regions=get_regions(),
                           services=get_services(),
                           categories=get_categories(),
                           kpis=kpis,
                           search=search,
                           sel_severity=severity,
                           sel_status=status,
                           sel_provider=provider,
                           page=page,
                           total_pages=total_pages,
                           total_count=total_count,
                           per_page=PER_PAGE)


# ── CREATE: add a new incident ───────────────────────────────
@app.route("/add", methods=["POST"])
def add_incident():
    try:
        f = request.form
        incident_id = str(uuid.uuid4())

        # compute duration if both times provided
        duration = f.get("duration_minutes") or None
        if f.get("start_time") and f.get("end_time") and not duration:
            fmt = "%Y-%m-%dT%H:%M"
            try:
                dt_start = datetime.strptime(f["start_time"], fmt)
                dt_end   = datetime.strptime(f["end_time"],   fmt)
                duration = int((dt_end - dt_start).total_seconds() / 60)
            except ValueError:
                duration = None

        execute_db("""
            INSERT INTO incidents (
                incident_id, provider_id, region_id, service_id, category_id,
                start_time, end_time, duration_minutes, severity, status,
                root_cause_description, customers_affected, revenue_loss_usd,
                sla_violation, region_impact_score, service_impact_score,
                ticket_count, detection_method, mitigation_action,
                engineers_involved, engineer_response_time_minutes,
                backup_triggered, post_mortem_completed, is_recurrent,
                external_factors, user_feedback_score,
                system_load_before, system_load_after, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            incident_id,
            int(f["provider_id"]),
            int(f["region_id"]),
            int(f["service_id"]),
            int(f["category_id"]) if f.get("category_id") else None,
            f.get("start_time", "").replace("T", " ") or None,
            f.get("end_time",   "").replace("T", " ") or None,
            duration,
            f["severity"],
            f["status"],
            f.get("root_cause_description") or None,
            int(f["customers_affected"])  if f.get("customers_affected")  else None,
            float(f["revenue_loss_usd"])  if f.get("revenue_loss_usd")    else None,
            1 if f.get("sla_violation") else 0,
            float(f["region_impact_score"])  if f.get("region_impact_score")  else None,
            float(f["service_impact_score"]) if f.get("service_impact_score") else None,
            int(f["ticket_count"])           if f.get("ticket_count")           else 0,
            f.get("detection_method")  or None,
            f.get("mitigation_action") or None,
            int(f["engineers_involved"])     if f.get("engineers_involved")     else 1,
            int(f["engineer_response_time_minutes"]) if f.get("engineer_response_time_minutes") else None,
            1 if f.get("backup_triggered")      else 0,
            1 if f.get("post_mortem_completed") else 0,
            1 if f.get("is_recurrent")          else 0,
            f.get("external_factors") or None,
            float(f["user_feedback_score"]) if f.get("user_feedback_score") else None,
            float(f["system_load_before"])  if f.get("system_load_before")  else None,
            float(f["system_load_after"])   if f.get("system_load_after")   else None,
            f.get("notes") or None,
        ))
        flash("✅ Incident added successfully.", "success")
    except Exception as e:
        flash(f"❌ Error adding incident: {e}", "danger")

    return redirect(url_for("index"))


# ── READ ONE: get incident JSON for edit modal ───────────────
@app.route("/incident/<incident_id>")
def get_incident(incident_id):
    row = query_db(INCIDENTS_JOIN + " WHERE i.incident_id = ?",
                   (incident_id,), one=True)
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


# ── UPDATE: edit an existing incident ───────────────────────
@app.route("/update/<incident_id>", methods=["POST"])
def update_incident(incident_id):
    try:
        f = request.form
        duration = f.get("duration_minutes") or None
        if f.get("start_time") and f.get("end_time") and not duration:
            fmt = "%Y-%m-%dT%H:%M"
            try:
                dt_start = datetime.strptime(f["start_time"], fmt)
                dt_end   = datetime.strptime(f["end_time"],   fmt)
                duration = int((dt_end - dt_start).total_seconds() / 60)
            except ValueError:
                duration = None

        execute_db("""
            UPDATE incidents SET
                provider_id              = ?,
                region_id                = ?,
                service_id               = ?,
                category_id              = ?,
                start_time               = ?,
                end_time                 = ?,
                duration_minutes         = ?,
                severity                 = ?,
                status                   = ?,
                root_cause_description   = ?,
                customers_affected       = ?,
                revenue_loss_usd         = ?,
                sla_violation            = ?,
                region_impact_score      = ?,
                service_impact_score     = ?,
                ticket_count             = ?,
                detection_method         = ?,
                mitigation_action        = ?,
                engineers_involved       = ?,
                engineer_response_time_minutes = ?,
                backup_triggered         = ?,
                post_mortem_completed    = ?,
                is_recurrent             = ?,
                external_factors         = ?,
                user_feedback_score      = ?,
                system_load_before       = ?,
                system_load_after        = ?,
                notes                    = ?
            WHERE incident_id = ?
        """, (
            int(f["provider_id"]),
            int(f["region_id"]),
            int(f["service_id"]),
            int(f["category_id"]) if f.get("category_id") else None,
            f.get("start_time", "").replace("T", " ") or None,
            f.get("end_time",   "").replace("T", " ") or None,
            duration,
            f["severity"],
            f["status"],
            f.get("root_cause_description") or None,
            int(f["customers_affected"])  if f.get("customers_affected")  else None,
            float(f["revenue_loss_usd"])  if f.get("revenue_loss_usd")    else None,
            1 if f.get("sla_violation") else 0,
            float(f["region_impact_score"])  if f.get("region_impact_score")  else None,
            float(f["service_impact_score"]) if f.get("service_impact_score") else None,
            int(f["ticket_count"])           if f.get("ticket_count")           else 0,
            f.get("detection_method")  or None,
            f.get("mitigation_action") or None,
            int(f["engineers_involved"])     if f.get("engineers_involved")     else 1,
            int(f["engineer_response_time_minutes"]) if f.get("engineer_response_time_minutes") else None,
            1 if f.get("backup_triggered")      else 0,
            1 if f.get("post_mortem_completed") else 0,
            1 if f.get("is_recurrent")          else 0,
            f.get("external_factors") or None,
            float(f["user_feedback_score"]) if f.get("user_feedback_score") else None,
            float(f["system_load_before"])  if f.get("system_load_before")  else None,
            float(f["system_load_after"])   if f.get("system_load_after")   else None,
            f.get("notes") or None,
            incident_id,
        ))
        flash("✅ Incident updated successfully.", "success")
    except Exception as e:
        flash(f"❌ Error updating incident: {e}", "danger")

    return redirect(url_for("index"))


# ── DELETE ───────────────────────────────────────────────────
@app.route("/delete/<incident_id>", methods=["POST"])
def delete_incident(incident_id):
    try:
        execute_db("DELETE FROM incidents WHERE incident_id = ?", (incident_id,))
        flash("🗑️ Incident deleted.", "warning")
    except Exception as e:
        flash(f"❌ Error deleting incident: {e}", "danger")
    return redirect(url_for("index"))


# ── ANALYTICS PAGE ───────────────────────────────────────────
@app.route("/analytics")
def analytics():
    return render_template("analytics.html")


# ── ANALYTICS JSON API  (consumed by Chart.js) ───────────────
@app.route("/api/analytics")
def api_analytics():

    # 1. Incidents by provider
    by_provider = query_db("""
        SELECT p.name AS label, COUNT(*) AS value
        FROM incidents i JOIN providers p ON i.provider_id = p.provider_id
        GROUP BY p.name ORDER BY value DESC
    """)

    # 2. Incidents by severity
    by_severity = query_db("""
        SELECT severity AS label, COUNT(*) AS value
        FROM incidents GROUP BY severity
        ORDER BY CASE severity
            WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
            WHEN 'Medium'   THEN 3 WHEN 'Low'  THEN 4 END
    """)

    # 3. Revenue loss by root cause
    by_cause = query_db("""
        SELECT c.name AS label,
               ROUND(SUM(i.revenue_loss_usd)/1000000.0, 2) AS value
        FROM incidents i
        JOIN root_cause_categories c ON i.category_id = c.category_id
        GROUP BY c.name ORDER BY value DESC
    """)

    # 4. Incidents by status
    by_status = query_db("""
        SELECT status AS label, COUNT(*) AS value
        FROM incidents GROUP BY status
    """)

    # 5. Avg duration by severity
    avg_duration = query_db("""
        SELECT severity AS label,
               ROUND(AVG(duration_minutes), 0) AS value
        FROM incidents GROUP BY severity
        ORDER BY CASE severity
            WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
            WHEN 'Medium'   THEN 3 WHEN 'Low'  THEN 4 END
    """)

    # 6. SLA violation rate by provider
    sla_rate = query_db("""
        SELECT p.name AS label,
               ROUND(100.0 * SUM(i.sla_violation) / COUNT(*), 1) AS value
        FROM incidents i JOIN providers p ON i.provider_id = p.provider_id
        GROUP BY p.name ORDER BY value DESC
    """)

    # 7. Customers affected by region  (top 8)
    by_region = query_db("""
        SELECT r.name AS label, SUM(i.customers_affected) AS value
        FROM incidents i JOIN regions r ON i.region_id = r.region_id
        GROUP BY r.name ORDER BY value DESC LIMIT 8
    """)

    # 8. Top KPI summary
    kpis = query_db("""
        SELECT COUNT(*)                                   AS total_incidents,
               ROUND(SUM(revenue_loss_usd)/1000000.0, 2) AS total_loss_m,
               SUM(customers_affected)                   AS total_customers,
               ROUND(AVG(duration_minutes), 0)           AS avg_duration_min,
               ROUND(100.0*SUM(sla_violation)/COUNT(*),1) AS sla_violation_pct,
               SUM(CASE WHEN status='Investigating' THEN 1 ELSE 0 END) AS open_incidents
        FROM incidents
    """, one=True)

    def rows_to_dict(rows):
        return [dict(r) for r in rows]

    return jsonify({
        "by_provider":   rows_to_dict(by_provider),
        "by_severity":   rows_to_dict(by_severity),
        "by_cause":      rows_to_dict(by_cause),
        "by_status":     rows_to_dict(by_status),
        "avg_duration":  rows_to_dict(avg_duration),
        "sla_rate":      rows_to_dict(sla_rate),
        "by_region":     rows_to_dict(by_region),
        "kpis":          dict(kpis),
    })


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print("[i] Database not found — initializing...")
        init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
