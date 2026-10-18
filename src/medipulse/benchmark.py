"""Honest before/after timing: no indexes -> indexes -> materialised view. Writes docs/performance.md."""
import statistics
import time
from pathlib import Path

from medipulse.cli import build
from medipulse.db import run_sql_file

LAST90 = "(SELECT max(full_date) - 90 FROM dwh.dim_date)"
CASES = [  # (label, view query, materialised alternative or None)
    ("Daily KPIs, last 90 days", f"SELECT * FROM mart.v_daily_kpis WHERE visit_date >= {LAST90}", None),
    ("Doctor utilisation, latest month",
     "SELECT * FROM mart.v_doctor_utilization WHERE month_start = (SELECT max(month_start) FROM dwh.dim_date)", None),
    ("Lab turnaround by test", "SELECT * FROM mart.v_lab_turnaround", None),
    ("30-day return rate (window fn)", "SELECT * FROM mart.v_return_rate", "SELECT * FROM mart.mv_return_rate"),
    ("Patient retention cohorts", "SELECT * FROM mart.v_patient_cohorts", "SELECT * FROM mart.mv_patient_cohorts"),
]


def _ms(conn, sql: str, runs: int = 3) -> float:
    with conn.cursor() as cur:
        cur.execute(sql); cur.fetchall()  # warm-up
        times = []
        for _ in range(runs):
            t = time.perf_counter(); cur.execute(sql); cur.fetchall()
            times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times)


def run(conn, visits: int) -> None:
    counts = build(conn, visits)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='dwh' AND indexname LIKE 'ix\\_%'")
        for (ix,) in cur.fetchall():
            cur.execute(f"DROP INDEX dwh.{ix}")
        cur.execute("ANALYZE")
    base = {label: _ms(conn, q) for label, q, _ in CASES}
    run_sql_file(conn, "03_indexes.sql")
    with conn.cursor() as cur:
        cur.execute("ANALYZE")
    idx = {label: _ms(conn, q) for label, q, _ in CASES}
    mat = {label: _ms(conn, m) for label, _, m in CASES if m}

    rows = ["| Query | No indexes (ms) | With indexes (ms) | Materialised (ms) | Speed-up vs baseline |",
            "|---|---:|---:|---:|---:|"]
    for label, _, m in CASES:
        best = mat.get(label, idx[label])
        rows.append(f"| {label} | {base[label]:,.1f} | {idx[label]:,.1f} | "
                    f"{(f'{mat[label]:,.1f}' if m else '-')} | {base[label] / best:,.1f}x |")
    md = (f"# Query performance\n\nSynthetic data: {counts['fact_visits']:,} visits, {counts['fact_lab_tests']:,} lab orders, "
          f"{counts['dim_patient']:,} patients. PostgreSQL, median of 3 warm runs.\n"
          f"Reproduce: `python -m medipulse benchmark --visits {visits}`.\n\n" + "\n".join(rows) + "\n")
    Path("docs").mkdir(exist_ok=True)
    Path("docs/performance.md").write_text(md)
    print(md)
