"""CLI:  python -m medipulse build|refresh|report|benchmark"""
import argparse

from medipulse.db import connect, copy_df, query, run_sql_file
from medipulse.generate import generate

LOAD_ORDER = ["dim_date", "dim_doctor", "dim_patient", "dim_test", "fact_visits", "fact_lab_tests"]


def build(conn, visits: int = 20000, seed: int = 42, start: str = "2025-10-01", days: int = 365) -> dict:
    """Rebuild schema, load synthetic data, create views / indexes / materialised views / grants."""
    run_sql_file(conn, "01_schema.sql")
    data = generate(visits, seed, start, days)
    for name in LOAD_ORDER:
        copy_df(conn, f"dwh.{name}", data[name])
    conn.commit()
    for f in ("02_views.sql", "03_indexes.sql", "04_materialized.sql", "05_security.sql"):
        run_sql_file(conn, f)
    with conn.cursor() as cur:
        cur.execute("ANALYZE")
    conn.commit()
    return {k: len(v) for k, v in data.items()}


def refresh(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW mart.mv_return_rate")
        cur.execute("REFRESH MATERIALIZED VIEW mart.mv_patient_cohorts")
        cur.execute("ANALYZE")
    conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser(prog="medipulse")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="rebuild warehouse + KPI layer from synthetic data")
    b.add_argument("--visits", type=int, default=20000)
    b.add_argument("--seed", type=int, default=42)
    sub.add_parser("refresh", help="refresh materialised views")
    r = sub.add_parser("report", help="write docs/dashboard_preview.png and print headline KPIs")
    r.add_argument("--out", default="docs/dashboard_preview.png")
    bm = sub.add_parser("benchmark", help="measure query speed with/without indexes and materialised views")
    bm.add_argument("--visits", type=int, default=300000)
    a = ap.parse_args()

    conn = connect()
    if a.cmd == "build":
        for t, n in build(conn, a.visits, a.seed).items():
            print(f"{t:16s}{n:>10,}")
    elif a.cmd == "refresh":
        refresh(conn)
        print("materialised views refreshed")
    elif a.cmd == "report":
        from medipulse.report import make_report
        make_report(conn, a.out)
    elif a.cmd == "benchmark":
        from medipulse.benchmark import run
        run(conn, a.visits)
    conn.close()
