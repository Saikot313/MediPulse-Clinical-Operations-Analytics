import os
import sys
import time
import requests

MB = os.getenv("METABASE_URL", "http://localhost:3000")
EMAIL = os.getenv("MB_ADMIN_EMAIL", "admin@medipulse.local")
PASSWORD = os.getenv("MB_ADMIN_PASSWORD", "MediPulse#2026x")
DB = {"host": os.getenv("MB_DB_HOST", "postgres"), "port": 5432, "dbname": "medipulse",
      "user": "bi_reader", "password": "bi_reader", "ssl": False}
DASH = "MediPulse - Clinical Operations"

# (name, sql, display, width, height)
CARDS = [
    ("Revenue, last 30 days (BDT)", "SELECT revenue_30d AS revenue FROM mart.v_exec_summary", "scalar", 6, 3),
    ("Completed visits, last 30 days", "SELECT completed_visits_30d AS visits FROM mart.v_exec_summary", "scalar", 6, 3),
    ("No-show rate, last 30 days (%)", "SELECT no_show_rate_30d AS rate FROM mart.v_exec_summary", "scalar", 6, 3),
    ("Average wait, last 30 days (min)", "SELECT avg_wait_min_30d AS wait FROM mart.v_exec_summary", "scalar", 6, 3),
    ("Monthly revenue", "SELECT month_start, revenue FROM mart.v_monthly_kpis ORDER BY 1", "bar", 12, 6),
    ("Weekly no-show rate (%)",
     "SELECT date_trunc('week', visit_date)::date AS week, round(100.0*sum(no_shows)/NULLIF(sum(completed_visits+no_shows),0),2) AS no_show_rate_pct FROM mart.v_daily_kpis GROUP BY 1 ORDER BY 1",
     "line", 12, 6),
    ("Revenue by department", "SELECT department, revenue FROM mart.v_department_scorecard ORDER BY revenue DESC", "bar", 12, 6),
    ("Visits by hour of day", "SELECT visit_hour, sum(visits) AS visits FROM mart.v_hourly_heatmap GROUP BY 1 ORDER BY 1", "bar", 12, 6),
    ("Lab orders resulted within target (%)", "SELECT test_name, pct_within_target FROM mart.v_lab_turnaround ORDER BY 2", "bar", 12, 6),
    ("30-day return rate by department (%)",
     "SELECT department, round(100.0*sum(returned_30d)/sum(completed_visits),1) AS return_rate_pct FROM mart.mv_return_rate GROUP BY 1 ORDER BY 2 DESC",
     "bar", 12, 6),
    ("Doctors above 90% utilisation (latest month)",
     "SELECT doctor, department, booked_slots, capacity_slots, utilization_pct FROM mart.v_doctor_utilization "
     "WHERE month_start = (SELECT max(month_start) FROM mart.v_doctor_utilization) AND utilization_pct > 90 ORDER BY 5 DESC",
     "table", 12, 6),
]


def wait_ready():
    for _ in range(60):
        try:
            if requests.get(f"{MB}/api/health", timeout=3).json().get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(5)
    sys.exit("Metabase is not reachable at " + MB)


def login() -> str:
    token = requests.get(f"{MB}/api/session/properties").json().get("setup-token")
    if token:  # first run: create admin + data source
        r = requests.post(f"{MB}/api/setup", json={
            "token": token,
            "user": {"first_name": "Admin", "last_name": "MediPulse", "email": EMAIL, "password": PASSWORD},
            "prefs": {"site_name": "MediPulse", "allow_tracking": False},
            "database": {"engine": "postgres", "name": "MediPulse", "details": DB}})
    else:
        r = requests.post(f"{MB}/api/session", json={"username": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["id"]


def main():
    wait_ready()
    h = {"X-Metabase-Session": login()}
    dbs = requests.get(f"{MB}/api/database", headers=h).json()
    dbs = dbs["data"] if isinstance(dbs, dict) else dbs
    db_id = next((d["id"] for d in dbs if d["name"] == "MediPulse"), None)
    if db_id is None:  # newer Metabase ignores the 'database' field of /api/setup
        r = requests.post(f"{MB}/api/database", headers=h,
                          json={"engine": "postgres", "name": "MediPulse", "details": DB})
        r.raise_for_status()
        db_id = r.json()["id"]
    existing = requests.get(f"{MB}/api/dashboard", headers=h).json()
    if any(d["name"] == DASH for d in existing):
        return print("dashboard already exists - nothing to do")
    dash = requests.post(f"{MB}/api/dashboard", headers=h, json={"name": DASH}).json()
    placed, row, col = [], 0, 0
    for i, (name, sql, display, w, ht) in enumerate(CARDS):
        card = requests.post(f"{MB}/api/card", headers=h, json={
            "name": name, "display": display, "visualization_settings": {},
            "dataset_query": {"type": "native", "database": db_id, "native": {"query": sql}}})
        card.raise_for_status()
        if col + w > 24:
            row, col = row + prev_h, 0
        placed.append({"id": -(i + 1), "card_id": card.json()["id"], "row": row, "col": col,
                       "size_x": w, "size_y": ht, "visualization_settings": {}, "parameter_mappings": []})
        col, prev_h = col + w, ht
    requests.put(f"{MB}/api/dashboard/{dash['id']}", headers=h, json={"dashcards": placed}).raise_for_status()
    print(f"dashboard ready: {MB}/dashboard/{dash['id']}")


if __name__ == "__main__":
    main()
