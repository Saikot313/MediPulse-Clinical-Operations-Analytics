<div align="center">

# 🩺 MediPulse

### Clinical Operations Analytics & BI Dashboard

**From raw hospital activity to decisions: 11 KPI views, SQL optimisation and a live Metabase dashboard on PostgreSQL.**

![Tests](https://img.shields.io/badge/tests-13%20passing-brightgreen)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Metabase](https://img.shields.io/badge/BI-Metabase-509EE3)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)
![Last commit](https://img.shields.io/github/last-commit/Saikot313/MediPulse-Clinical-Operations-Analytics)

[Dashboard](#-dashboard) · [Findings](#-what-the-data-says) · [Architecture](#-architecture) · [Performance](#-query-optimisation-measured) · [Quick start](#-quick-start) · [Screenshots](#-screenshots)

<br>

<img src="screenshots/metabase_dashboard.png" alt="MediPulse Metabase dashboard" width="100%">

</div>

---

## ✨ At a glance

| | |
|---|---|
| **11** KPI views + **2** materialised views | **13** integration tests on real PostgreSQL |
| **20,000** visits, **8.5k** lab orders (default demo) | **300,000** visits used for benchmarks |
| **0.1 ms** return-rate query after materialising (from 241 ms) | **0** patient identifiers exposed to BI users |

MediPulse is the analytics half of a healthcare data series. [**MediFlow**](https://github.com/Saikot313/MediFlow-Healthcare-ETL-Pipeline) moves and validates the data; **MediPulse** turns it into answers a hospital manager can act on. It follows the same `dwh` star schema, `mart` view layer and read-only `bi_reader` pattern, so the two projects fit together.

## 🎯 What it answers

| A manager asks | View | Technique |
|---|---|---|
| How are revenue, visits, no-shows and waits vs the previous month? | `v_exec_summary`, `v_monthly_kpis` | `LAG`, 30-vs-30-day comparison |
| Which departments earn most, and where do patients wait? | `v_department_scorecard` | `percentile_cont` (P90), `RANK` |
| Which doctors are overbooked or underused? | `v_doctor_utilization` | capacity model (slots × working days) |
| When is the clinic busiest? | `v_hourly_heatmap` | weekday × hour aggregation |
| Which lab tests miss their target, and when? | `v_lab_turnaround`, `v_lab_tat_by_hour` | P50 / P90, % within target |
| Do patients return within 30 days? | `v_return_rate` | `LEAD`, right-censoring handled |
| Do new patients stay engaged? | `v_patient_cohorts` | cohort retention matrix |
| Who is most likely to no-show? | `v_noshow_drivers` | segment comparison |

<details>
<summary><b>📐 KPI definitions (click to expand)</b></summary>

- **No-show rate** = no-shows ÷ (completed + no-shows). Cancellations are excluded because a cancelled slot can be rebooked.
- **Revenue** = `net_amount` of *completed* visits only (fee − discount).
- **Utilisation** = booked (non-cancelled) slots ÷ (slots per day × working days). Friday and Saturday are the weekend.
- **30-day return** = completed visit followed by another completed visit within 30 days. Visits in the final 30 days of data are excluded, because their outcome is not yet known (right-censoring).
- **Retention cohort** = patients grouped by month of first completed visit. The first cohort is left-censored (includes patients active before the data starts).
- **Lab within target** = turnaround ≤ the test's target minutes, among resulted orders.

</details>

## 📊 Dashboard

Metabase dashboard with 11 cards, created automatically by [`metabase/provision.py`](metabase/provision.py). Every card reads from the `mart` schema only.

<div align="center">
<img src="screenshots/metabase_sql_card.png" alt="A dashboard card and its SQL" width="92%">
<br><sub>Each card is a plain SQL query on a <code>mart</code> view: no raw tables, no patient data.</sub>
</div>

## 🔎 What the data says

> Findings describe the **synthetic** data generator (seed 42, Oct 2025 to Sep 2026), which has these patterns built in on purpose. They are not clinical claims.

| 🔬 Finding | Evidence |
|---|---|
| **Lab turnaround collapses after 15:00** | Orders placed after 15:00 are resulted within target about 63-65% of the time, against about 80-84% in the morning. Overall: 75.9%. Thyroid Panel and HbA1c are the slowest tests. |
| **Payer type drives no-shows** | Self-pay 15.5% vs Corporate 9.1%. New-patient visits 15.6% vs follow-ups 14.3%. A reminder campaign should start with self-pay first visits. |
| **Cardiology leads revenue** | BDT 3.34M, rank 1. Neurology ranks last on revenue but has the lowest no-show rate (about 10%). |
| **Capacity is fine on average, tight at the edges** | Average utilisation 55%, but 2 doctor-months exceed 100% (one ENT doctor sits at 97.7% in the latest month). |
| **Last 30 days softened** | Revenue −7.0% and no-shows +0.6 pts vs the previous 30 days (seasonal dip in the generator). |

<div align="center">
<img src="screenshots/sql_lab_insight.png" alt="Lab turnaround by hour of day" width="70%">
<br><sub>Lab insight straight from SQL: <code>mart.v_lab_tat_by_hour</code>.</sub>
</div>

## 🏗 Architecture

```mermaid
flowchart LR
    G["generate.py<br/>seeded synthetic data"] -->|COPY| DWH
    subgraph PG["PostgreSQL 16"]
        direction LR
        DWH[("dwh<br/>star schema")] --> V["mart<br/>11 KPI views"]
        V --> MV["2 materialised<br/>views"]
    end
    V -->|"read-only role<br/>bi_reader"| MB["Metabase<br/>dashboard"]
    MV --> MB
```

<details>
<summary><b>🗂 Data model (click to expand)</b></summary>

```mermaid
erDiagram
    dim_date    ||--o{ fact_visits    : date_key
    dim_patient ||--o{ fact_visits    : patient_key
    dim_doctor  ||--o{ fact_visits    : doctor_key
    fact_visits ||--o{ fact_lab_tests : visit_key
    dim_test    ||--o{ fact_lab_tests : test_key

    fact_visits {
        int visit_key PK
        text status "Completed, No-Show, Cancelled"
        text visit_type "New, Follow-up, Emergency"
        int wait_minutes
        numeric net_amount "fee minus discount"
    }
    fact_lab_tests {
        int lab_key PK
        int turnaround_minutes
        text result_flag "Normal, High, Low, Pending"
    }
    dim_doctor {
        int doctor_key PK
        text department
        int slots_per_day
    }
    dim_patient {
        int patient_key PK
        text patient_token "pseudonymous"
        text age_band
        text insurance_type
    }
```

Grain: `fact_visits` is one row per scheduled visit; `fact_lab_tests` is one row per lab order. CHECK and foreign-key constraints enforce rules such as `net_amount = consultation_fee − discount`.

</details>

## ⚡ Query optimisation (measured)

300,000 visits, 129,586 lab orders, 100,000 patients. Median of 3 warm runs. Reproduce with `python -m medipulse benchmark --visits 300000`.

| Query | No indexes | Indexed | Materialised |
|---|---:|---:|---:|
| Doctor utilisation, latest month | 27.1 ms | **6.2 ms** (4.4×) | n/a |
| 30-day return rate (window function) | 241.0 ms | 215.6 ms | **0.1 ms** |
| Patient retention cohorts | 271.5 ms | 287.5 ms | **0.1 ms** |
| Daily KPIs, last 90 days | 43.6 ms | 45.7 ms | n/a |
| Lab turnaround by test | 92.3 ms | 84.7 ms | n/a |

**The honest reading:** indexes help selective lookups (utilisation), do nothing for full-scan aggregates, and cannot fix window-function views. For those, a materialised view refreshed after each load is the right tool (`python -m medipulse refresh`). Every index in [`sql/03_indexes.sql`](sql/03_indexes.sql) exists because a view needs it, and the benchmark shows where indexes did *not* help.

<div align="center">
<img src="screenshots/benchmark.png" alt="Benchmark output" width="85%">
</div>

## 🔐 Security by design

- `mart` contains **no patient identifiers**; `dwh.dim_patient` holds only a pseudonymous token and an age band.
- BI users connect as `bi_reader`, which can read `mart` but has **no access to `dwh`**. This is tested automatically.

<div align="center">
<img src="screenshots/security_bi_reader.png" alt="bi_reader permission denied on dwh" width="70%">
<br><sub><code>bi_reader</code> reads <code>mart</code> but gets <code>permission denied</code> on <code>dwh</code>.</sub>
</div>

## ✅ Testing

13 integration tests run against a real PostgreSQL:

- dashboard totals **reconcile** to the fact tables (revenue, visit counts)
- KPI formulas **recomputed independently** and compared
- month-over-month is NULL for the first month; cohort month 0 = 100%
- each materialised view **equals** its source view
- lab orders = resulted + pending
- `bi_reader` can read `mart` and is denied on `dwh`
- the data generator is deterministic for a given seed

<div align="center">
<img src="screenshots/terminal_tests.png" alt="13 tests passing" width="85%">
<br><sub>13 passed locally</sub>
</div>

## 🚀 Quick start

**Requirements:** Docker Desktop and Python 3.11+.

```powershell
# 1. Install
git clone https://github.com/Saikot313/MediPulse-Clinical-Operations-Analytics.git
cd MediPulse-Clinical-Operations-Analytics
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:PYTHONPATH="src"

# 2. Database + warehouse
docker compose up -d postgres
python -m medipulse build            # schema + 20k visits + views + indexes + materialised views

# 3. Dashboard
docker compose --profile bi up -d    # Metabase on http://localhost:3000 (first start takes 1-3 min)
python metabase\provision.py         # creates the data source and the dashboard
```

Log in at <http://localhost:3000> with `admin@medipulse.local` / `MediPulse#2026x` (local demo credentials; override with `MB_ADMIN_EMAIL` and `MB_ADMIN_PASSWORD`). The dashboard is under **Our analytics → MediPulse - Clinical Operations**.

<details>
<summary><b>🐧 macOS / Linux</b></summary>

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
docker compose up -d postgres
python -m medipulse build
docker compose --profile bi up -d
python metabase/provision.py
```
</details>

<details>
<summary><b>🧪 Run the tests</b></summary>

Tests need their own database because they **drop the `dwh` and `mart` schemas** of the target.

```powershell
docker compose exec postgres createdb -U warehouse medipulse_test
$env:MEDIPULSE_TEST_URL="postgresql://warehouse:warehouse@localhost:5432/medipulse_test"
python -m pytest -v
```
</details>

<details>
<summary><b>🛠 All commands</b></summary>

| Command | What it does |
|---|---|
| `python -m medipulse build [--visits N] [--seed S]` | Rebuild schema, load data, create views, indexes, materialised views, grants |
| `python -m medipulse refresh` | Refresh the materialised views |
| `python -m medipulse report` | Write `docs/dashboard_preview.png` |
| `python -m medipulse benchmark --visits 300000` | Time queries with and without indexes and materialised views |

Without local Python: `docker compose --profile tools run --rm app build`.
</details>

<details>
<summary><b>🩹 Troubleshooting</b></summary>

| Problem | Fix |
|---|---|
| `No module named medipulse` | Set `$env:PYTHONPATH="src"` (once per new terminal) |
| `connection refused` | Start Docker Desktop, then `docker compose up -d postgres` |
| Metabase shows a sample "E-commerce Insights" dashboard | That is Metabase's built-in demo. Open **Our analytics** and pick the MediPulse dashboard |
| Dashboard empty | Run `python -m medipulse build`, then refresh the browser |
| Start from scratch | `docker compose --profile bi down -v`, then build and provision again |
</details>

## 🖼 Screenshots

<table>
<tr>
<td width="50%"><img src="screenshots/terminal_build.png" alt="Warehouse build"><br><sub><b>Warehouse build</b>: 6 tables loaded in seconds</sub></td>
<td width="50%"><img src="screenshots/sql_exec_summary.png" alt="Executive summary view"><br><sub><b>Executive summary</b> view queried in psql</sub></td>
</tr>
</table>

## 📁 Project structure

```
MediPulse/
├── sql/
│   ├── 01_schema.sql          # star schema + constraints
│   ├── 02_views.sql           # 11 KPI views (mart)
│   ├── 03_indexes.sql         # query-driven indexes
│   ├── 04_materialized.sql    # materialised heavy views
│   └── 05_security.sql        # bi_reader: mart only
├── src/medipulse/             # generate, build/refresh CLI, report, benchmark
├── metabase/provision.py      # data source + 11-card dashboard via API
├── tests/test_medipulse.py    # 13 integration tests
├── docs/                      # performance.md, dashboard preview
├── screenshots/
└── docker-compose.yml  Dockerfile  Makefile
```

## 🧭 Design decisions

- **SQL does the analytics.** Python only generates data, draws the preview image and drives the CLI. Logic lives where a BI tool or analyst can reuse it.
- **Measure before optimising.** The benchmark records where indexes did not help, so each optimisation is justified by a number.
- **Define KPIs explicitly.** Denominators, exclusions and censoring rules are written down, because a KPI without a definition is an opinion.
- **Least privilege.** The BI role reads only the pseudonymised `mart` schema.
- **Reproducible.** A fixed seed makes every number in this README reproducible on any machine.

## ⚠️ Limitations

- All data is **synthetic** (currency BDT). Findings describe the generator, not real hospitals.
- The Metabase provisioning script was written against the v0.50 API and tested on a recent Metabase image; other versions may need small payload changes.
- The first retention cohort is left-censored by the data window.

## 🗺 Roadmap

- [ ] Point the views at MediFlow's live warehouse instead of the generator
- [ ] Data-freshness checks and alerting
- [ ] Daily demand forecasting
- [ ] Table partitioning for the fact tables at larger scale

## 👤 Author

**Md. Sakender Saikot**: BSc in CSE, MSc Data Science (AIUB), moving into data and ML engineering.
[GitHub @Saikot313](https://github.com/Saikot313)

Released under the [MIT License](LICENSE). All data in this repository is synthetic.
