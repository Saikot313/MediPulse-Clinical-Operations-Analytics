"""Integration tests on a real PostgreSQL. WARNING: they DROP the dwh and mart schemas of MEDIPULSE_TEST_URL."""
import os

import psycopg2
import pytest

from medipulse.cli import build
from medipulse.db import connect, query
from medipulse.generate import generate

N = 3000
URL = os.getenv("MEDIPULSE_TEST_URL")
needs_db = pytest.mark.skipif(not URL, reason="set MEDIPULSE_TEST_URL to run integration tests")


def scalar(conn, sql):
    return query(conn, sql).iloc[0, 0]


@pytest.fixture(scope="module")
def conn():
    c = connect(URL)
    build(c, visits=N, seed=7)
    yield c
    c.close()


def test_generator_is_deterministic():
    a, b = generate(500, seed=1), generate(500, seed=1)
    for k in a:
        assert a[k].equals(b[k]), k
    assert not generate(500, seed=2)["fact_visits"].equals(a["fact_visits"])


@needs_db
def test_row_counts_and_keys(conn):
    assert scalar(conn, "SELECT count(*) FROM dwh.fact_visits") == N
    orphan = scalar(conn, """SELECT count(*) FROM dwh.fact_lab_tests l
                             LEFT JOIN dwh.fact_visits v USING (visit_key) WHERE v.visit_key IS NULL""")
    assert orphan == 0
    assert scalar(conn, "SELECT count(*) FROM dwh.fact_lab_tests l JOIN dwh.fact_visits v USING (visit_key) WHERE v.status <> 'Completed'") == 0


@needs_db
def test_daily_kpis_reconcile_with_facts(conn):
    fact = scalar(conn, "SELECT sum(net_amount) FROM dwh.fact_visits WHERE status = 'Completed'")
    assert scalar(conn, "SELECT sum(revenue) FROM mart.v_daily_kpis") == fact
    assert scalar(conn, "SELECT sum(revenue) FROM mart.v_monthly_kpis") == fact
    assert scalar(conn, "SELECT sum(completed_visits + no_shows + cancellations) FROM mart.v_daily_kpis") == N


@needs_db
def test_no_show_rate_definition(conn):
    r = query(conn, "SELECT * FROM mart.v_daily_kpis WHERE completed_visits + no_shows > 0")
    expected = (100.0 * r.no_shows / (r.completed_visits + r.no_shows)).astype(float)
    assert (abs(r.no_show_rate_pct.astype(float) - expected) < 0.01).all()
    assert r.no_show_rate_pct.astype(float).between(0, 100).all()


@needs_db
def test_month_over_month_first_month_is_null(conn):
    m = query(conn, "SELECT revenue_mom_pct FROM mart.v_monthly_kpis ORDER BY month_start")
    assert m.revenue_mom_pct.iloc[0] is None or m.revenue_mom_pct.isna().iloc[0]
    assert m.revenue_mom_pct.iloc[1:].notna().all()


@needs_db
def test_department_scorecard(conn):
    assert scalar(conn, "SELECT sum(scheduled_visits) FROM mart.v_department_scorecard") == N
    assert scalar(conn, "SELECT revenue_rank FROM mart.v_department_scorecard ORDER BY revenue DESC LIMIT 1") == 1
    assert abs(float(scalar(conn, "SELECT sum(revenue_share_pct) FROM mart.v_department_scorecard")) - 100) < 0.5


@needs_db
def test_doctor_utilization_is_consistent(conn):
    u = query(conn, "SELECT * FROM mart.v_doctor_utilization")
    assert (u.capacity_slots > 0).all()
    assert (u.completed_visits <= u.booked_slots).all()
    assert u.utilization_pct.astype(float).max() < 250  # sanity bound; capacity sized from real load


@needs_db
def test_return_rate_and_materialized_view_match(conn):
    r = query(conn, "SELECT * FROM mart.v_return_rate")
    assert (r.returned_30d <= r.completed_visits).all()
    diff = scalar(conn, """SELECT count(*) FROM (
        (SELECT * FROM mart.v_return_rate EXCEPT SELECT * FROM mart.mv_return_rate)
        UNION ALL (SELECT * FROM mart.mv_return_rate EXCEPT SELECT * FROM mart.v_return_rate)) x""")
    assert diff == 0


@needs_db
def test_return_rate_excludes_censored_tail(conn):
    mx = scalar(conn, "SELECT max(full_date) FROM dwh.dim_date")
    last = scalar(conn, "SELECT max(month_start) FROM mart.v_return_rate")
    assert (mx - last).days >= 30  # no visit newer than (data end - 30 days) is evaluated


@needs_db
def test_cohort_month_zero_is_100_percent(conn):
    z = query(conn, "SELECT retention_pct FROM mart.v_patient_cohorts WHERE months_since = 0")
    assert (z.retention_pct.astype(float) == 100.0).all()


@needs_db
def test_lab_turnaround(conn):
    t = query(conn, "SELECT * FROM mart.v_lab_turnaround")
    assert (t.orders == t.resulted + t.pending).all()
    assert t.pct_within_target.astype(float).between(0, 100).all()
    assert t.orders.sum() == scalar(conn, "SELECT count(*) FROM dwh.fact_lab_tests")


@needs_db
def test_exec_summary_single_row(conn):
    assert len(query(conn, "SELECT * FROM mart.v_exec_summary")) == 1


@needs_db
def test_bi_reader_reads_mart_but_not_dwh(conn):
    with conn.cursor() as cur:
        cur.execute("SET ROLE bi_reader")
        cur.execute("SELECT count(*) FROM mart.v_daily_kpis")
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("SELECT * FROM dwh.dim_patient")
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("RESET ROLE")
    conn.commit()
