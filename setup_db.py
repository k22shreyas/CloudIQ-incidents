"""Initialize or reset the Cloud Incidents SQLite database.

Run this before starting the Flask app:
    python setup_db.py

The script rebuilds the schema and bulk-loads incidents from a CSV file.
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "cloud_incidents.db"
SQL_PATH = BASE_DIR / "database" / "schema.sql"

CSV_FILENAME = "cloud_outages_dataset.csv"

CSV_CANDIDATES = [
    BASE_DIR / CSV_FILENAME,
    BASE_DIR / "database" / CSV_FILENAME,
    BASE_DIR / "data" / CSV_FILENAME,
]

INCIDENT_COLUMNS = [
    "incident_id",
    "provider_id",
    "region_id",
    "service_id",
    "category_id",
    "start_time",
    "end_time",
    "duration_minutes",
    "severity",
    "status",
    "root_cause_description",
    "customers_affected",
    "revenue_loss_usd",
    "sla_violation",
    "region_impact_score",
    "service_impact_score",
    "ticket_count",
    "detection_method",
    "mitigation_action",
    "engineers_involved",
    "engineer_response_time_minutes",
    "backup_triggered",
    "post_mortem_completed",
    "is_recurrent",
    "external_factors",
    "scheduled_maintenance_conflict",
    "patch_applied",
    "system_load_before",
    "system_load_after",
    "user_feedback_score",
    "notes",
]

REQUIRED_COLUMNS = {
    "incident_id",
    "provider_id",
    "region_id",
    "service_id",
    "start_time",
    "severity",
    "status",
}

BOOL_COLUMNS = {
    "sla_violation",
    "backup_triggered",
    "post_mortem_completed",
    "is_recurrent",
    "scheduled_maintenance_conflict",
    "patch_applied",
}

INT_COLUMNS = {
    "provider_id",
    "region_id",
    "service_id",
    "category_id",
    "duration_minutes",
    "customers_affected",
    "ticket_count",
    "engineers_involved",
    "engineer_response_time_minutes",
}

FLOAT_COLUMNS = {
    "revenue_loss_usd",
    "region_impact_score",
    "service_impact_score",
    "system_load_before",
    "system_load_after",
    "user_feedback_score",
}

TEXT_COLUMNS = {
    "incident_id",
    "start_time",
    "end_time",
    "severity",
    "status",
    "root_cause_description",
    "detection_method",
    "mitigation_action",
    "external_factors",
    "notes",
}


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def coerce_bool(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "on"}:
        return 1
    if text in {"0", "false", "f", "no", "n", "off", ""}:
        return 0
    raise ValueError(f"Cannot interpret boolean value: {value!r}")


def coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return int(float(text))


def coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return float(text)


def coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text != "" else None


def find_csv_path() -> Path:
    for candidate in CSV_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists() and path.is_file():
            return path
    searched = "\n".join(str(Path(c)) for c in CSV_CANDIDATES if c)
    raise FileNotFoundError(
        f"Could not find the incidents CSV file. Set {CSV_ENV_VAR} or place incidents.csv in one of:\n{searched}"
    )


def load_lookup_maps(conn: sqlite3.Connection) -> Dict[str, Dict[str, int]]:
    lookups: Dict[str, Dict[str, int]] = {
        "providers": {},
        "regions": {},
        "services": {},
        "categories": {},
    }

    for row in conn.execute("SELECT provider_id, name FROM providers"):
        lookups["providers"][normalize_key(row[1])] = row[0]

    for row in conn.execute("SELECT region_id, name FROM regions"):
        lookups["regions"][normalize_key(row[1])] = row[0]

    for row in conn.execute("SELECT service_id, name, subtype FROM services"):
        service_id, name, subtype = row
        lookups["services"][normalize_key(name)] = service_id
        if subtype:
            lookups["services"][normalize_key(f"{name}_{subtype}")] = service_id
            lookups["services"][normalize_key(subtype)] = service_id

    for row in conn.execute("SELECT category_id, name FROM root_cause_categories"):
        lookups["categories"][normalize_key(row[1])] = row[0]

    return lookups


def resolve_lookup(row: Dict[str, Any], lookup_maps: Dict[str, Dict[str, int]], kind: str) -> Optional[int]:
    candidates = {
        "providers": ["provider_id", "provider", "provider_name", "cloud_provider"],
        "regions": ["region_id", "region", "region_name"],
        "services": ["service_id", "service", "service_name", "service_type", "subtype"],
        "categories": ["category_id", "category", "category_name", "root_cause_category"],
    }[kind]

    for key in candidates:
        if key not in row:
            continue
        value = row[key]
        if value in (None, ""):
            continue
        if key.endswith("_id"):
            return coerce_int(value)
        mapped = lookup_maps[kind].get(normalize_key(str(value)))
        if mapped is not None:
            return mapped
    return None


def read_csv_rows(csv_path: Path) -> List[Dict[str, Any]]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV file has no header row.")
        rows: List[Dict[str, Any]] = []
        for raw_row in reader:
            normalized = {normalize_key(k): v for k, v in raw_row.items() if k is not None}
            rows.append(normalized)
    return rows


# Maps DB column names → alternative CSV-normalized column names
CSV_COLUMN_ALIASES: Dict[str, str] = {
    "customers_affected":        "number_of_customers_affected",
    "revenue_loss_usd":          "estimated_revenue_loss_usd",
    "engineers_involved":        "number_of_engineers_involved",
    "backup_triggered":          "backup_system_triggered",
    "is_recurrent":              "is_recurrent_issue",
    "system_load_before":        "system_load_before_outage",
    "system_load_after":         "system_load_after_outage",
}


def build_incident_row(
    row: Dict[str, Any],
    lookup_maps: Dict[str, Dict[str, int]],
) -> Tuple[Any, ...]:
    values: Dict[str, Any] = {}

    values["incident_id"] = coerce_text(row.get("incident_id")) or coerce_text(row.get("id"))
    values["provider_id"] = resolve_lookup(row, lookup_maps, "providers")
    values["region_id"] = resolve_lookup(row, lookup_maps, "regions")
    values["service_id"] = resolve_lookup(row, lookup_maps, "services")
    values["category_id"] = resolve_lookup(row, lookup_maps, "categories")

    if values["provider_id"] is None or values["region_id"] is None or values["service_id"] is None:
        missing = [name for name in ("provider_id", "region_id", "service_id") if values[name] is None]
        raise ValueError(
            f"Missing required lookup values {missing} for incident {values['incident_id'] or '<unknown>'}."
        )

    for col in INCIDENT_COLUMNS:
        if col in values:
            continue
        raw = row.get(col) if row.get(col) is not None else row.get(CSV_COLUMN_ALIASES.get(col, ""))
        if col in BOOL_COLUMNS:
            values[col] = coerce_bool(raw)
        elif col in INT_COLUMNS:
            values[col] = coerce_int(raw)
        elif col in FLOAT_COLUMNS:
            values[col] = coerce_float(raw)
        else:
            values[col] = coerce_text(raw)

    for col in REQUIRED_COLUMNS:
        if values.get(col) in (None, ""):
            raise ValueError(f"CSV row is missing required column '{col}' for incident {values.get('incident_id')!r}.")

    return tuple(values[col] for col in INCIDENT_COLUMNS)


def import_incidents(conn: sqlite3.Connection, csv_path: Path) -> int:
    rows = read_csv_rows(csv_path)
    lookup_maps = load_lookup_maps(conn)

    records: List[Tuple[Any, ...]] = []
    for idx, row in enumerate(rows, start=1):
        try:
            records.append(build_incident_row(row, lookup_maps))
        except Exception as exc:
            raise ValueError(f"Failed to parse CSV row {idx}: {exc}") from exc

    placeholders = ", ".join(["?"] * len(INCIDENT_COLUMNS))
    columns_sql = ", ".join(INCIDENT_COLUMNS)
    conn.executemany(
        f"INSERT INTO incidents ({columns_sql}) VALUES ({placeholders})",
        records,
    )
    return len(records)


def main() -> None:
    if DB_PATH.exists():
        print(f"[!] Removing existing database: {DB_PATH}")
        DB_PATH.unlink()

    print(f"[i] Running schema from: {SQL_PATH}")
    sql = SQL_PATH.read_text(encoding="utf-8")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(sql)

        csv_path = find_csv_path()
        print(f"[i] Loading incidents from CSV: {csv_path}")
        n = import_incidents(conn, csv_path)

        conn.commit()
        cur = conn.execute("SELECT COUNT(*) FROM incidents")
        total = cur.fetchone()[0]
    finally:
        conn.close()

    print(f"[✓] Database created: {DB_PATH}")
    print(f"[✓] Seeded lookup tables and loaded {n} incidents.")
    print(f"[✓] Incident row count verified: {total}")
    print("\n  Run the app with:  python app.py")
    print("  Then open:         http://127.0.0.1:5000\n")


if __name__ == "__main__":
    main()
