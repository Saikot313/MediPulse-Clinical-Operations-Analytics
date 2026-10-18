"""Static dashboard preview built from the mart views (same numbers Metabase shows)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from medipulse.db import query

C = {"main": "#0F766E", "accent": "#F59E0B", "bad": "#DC2626", "grey": "#94A3B8"}


def make_report(conn, out: str) -> None:
    ex = query(conn, "SELECT * FROM mart.v_exec_summary").iloc[0]
    mon = query(conn, "SELECT * FROM mart.v_monthly_kpis ORDER BY month_start")
    day = query(conn, "SELECT visit_date, no_show_rate_pct, completed_visits, no_shows FROM mart.v_daily_kpis ORDER BY 1")
    dep = query(conn, "SELECT * FROM mart.v_department_scorecard ORDER BY revenue")
    hm = query(conn, "SELECT dow, visit_hour, visits FROM mart.v_hourly_heatmap")
    lab = query(conn, "SELECT * FROM mart.v_lab_turnaround ORDER BY pct_within_target")
    coh = query(conn, "SELECT * FROM mart.mv_patient_cohorts")
    ret = query(conn, "SELECT department, 100.0*sum(returned_30d)/sum(completed_visits) AS r FROM mart.mv_return_rate GROUP BY 1 ORDER BY 2")

    fig = plt.figure(figsize=(17, 11), facecolor="white")
    gs = fig.add_gridspec(3, 3, top=0.79, hspace=0.5, wspace=0.28, left=0.05, right=0.98, bottom=0.05)
    fig.suptitle("MediPulse - Clinical Operations Dashboard (synthetic data)", fontsize=18, fontweight="bold", x=0.05, ha="left", y=0.97)
    kpis = [("Revenue, last 30d (BDT)", f"{float(ex.revenue_30d):,.0f}", f"{ex.revenue_change_pct:+.1f}% vs prior 30d"),
            ("Completed visits, 30d", f"{int(ex.completed_visits_30d):,}", f"{ex.completed_change_pct:+.1f}% vs prior 30d"),
            ("No-show rate, 30d", f"{float(ex.no_show_rate_30d):.1f}%", f"{ex.no_show_change_pts:+.1f} pts vs prior 30d"),
            ("Avg wait, 30d", f"{float(ex.avg_wait_min_30d):.1f} min", f"{ex.wait_change_min:+.1f} min vs prior 30d")]
    for i, (t, v, d) in enumerate(kpis):
        x = 0.05 + i * 0.238
        fig.text(x, 0.915, t, fontsize=10, color="#475569")
        fig.text(x, 0.885, v, fontsize=20, fontweight="bold", color=C["main"])
        fig.text(x, 0.868, d, fontsize=9, color="#64748B")

    ax = fig.add_subplot(gs[0, 0])
    ax.bar(mon.month_name, mon.revenue.astype(float) / 1e6, color=C["main"]); ax.set_title("Monthly revenue (M BDT)", loc="left")
    ax.tick_params(axis="x", rotation=60, labelsize=8)

    ax = fig.add_subplot(gs[0, 1])
    s = day.set_index("visit_date").no_show_rate_pct.astype(float)
    ax.plot(s.index, s.rolling(14, min_periods=5).mean(), color=C["bad"]); ax.set_title("No-show rate, 14-day average (%)", loc="left")
    ax.tick_params(axis="x", rotation=30, labelsize=8)

    ax = fig.add_subplot(gs[0, 2])
    ax.barh(dep.department, dep.revenue.astype(float) / 1e6, color=C["main"]); ax.set_title("Revenue by department (M BDT)", loc="left")

    ax = fig.add_subplot(gs[1, 0])
    grid = np.zeros((7, 10))
    for r in hm.itertuples():
        grid[int(r.dow), int(r.visit_hour) - 8] = r.visits
    im = ax.imshow(grid, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(10)); ax.set_xticklabels(range(8, 18)); ax.set_yticks(range(7)); ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    ax.set_title("Visit volume: weekday x hour", loc="left"); fig.colorbar(im, ax=ax, fraction=0.04)

    ax = fig.add_subplot(gs[1, 1])
    ax.barh(lab.test_name, lab.pct_within_target.astype(float), color=[C["bad"] if v < 80 else C["main"] for v in lab.pct_within_target.astype(float)])
    ax.axvline(80, color=C["grey"], ls="--", lw=1); ax.set_title("Lab orders resulted within target (%)", loc="left"); ax.tick_params(axis="y", labelsize=8)

    ax = fig.add_subplot(gs[1, 2])
    ax.barh(ret.department, ret.r.astype(float), color=C["accent"]); ax.set_title("30-day return rate (%)", loc="left")

    ax = fig.add_subplot(gs[2, 0:2])
    piv = coh.pivot(index="cohort_month", columns="months_since", values="retention_pct").astype(float)
    im = ax.imshow(piv.values, cmap="Greens", aspect="auto", vmin=0, vmax=60)
    ax.set_yticks(range(len(piv))); ax.set_yticklabels([str(d)[:7] for d in piv.index], fontsize=8)
    ax.set_xlabel("Months since first completed visit"); ax.set_title("Patient retention by first-visit cohort (%)", loc="left"); fig.colorbar(im, ax=ax, fraction=0.03)

    ax = fig.add_subplot(gs[2, 2])
    d = query(conn, "SELECT segment, no_show_rate_pct FROM mart.v_noshow_drivers WHERE dimension='Insurance' ORDER BY 2")
    ax.barh(d.segment, d.no_show_rate_pct.astype(float), color=C["bad"]); ax.set_title("No-show rate by insurance (%)", loc="left")

    for a in fig.axes:
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
    fig.savefig(out, dpi=110); print(f"wrote {out}")
