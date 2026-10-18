-- KPI layer: every view reads dwh only and exposes no patient identifiers.

CREATE VIEW mart.v_daily_kpis AS
SELECT d.full_date AS visit_date,
       count(*) AS scheduled_visits,
       count(*) FILTER (WHERE f.status = 'Completed') AS completed_visits,
       count(*) FILTER (WHERE f.status = 'No-Show')   AS no_shows,
       count(*) FILTER (WHERE f.status = 'Cancelled') AS cancellations,
       round(100.0 * count(*) FILTER (WHERE f.status = 'No-Show')
             / NULLIF(count(*) FILTER (WHERE f.status IN ('Completed','No-Show')), 0), 2) AS no_show_rate_pct,
       coalesce(sum(f.net_amount) FILTER (WHERE f.status = 'Completed'), 0) AS revenue,
       round(avg(f.wait_minutes) FILTER (WHERE f.status = 'Completed'), 1) AS avg_wait_min
FROM dwh.fact_visits f JOIN dwh.dim_date d USING (date_key)
GROUP BY d.full_date;

CREATE VIEW mart.v_monthly_kpis AS
WITH m AS (
  SELECT d.month_start, min(d.month_name) AS month_name,
         count(*) AS scheduled_visits,
         count(*) FILTER (WHERE f.status = 'Completed') AS completed_visits,
         count(*) FILTER (WHERE f.status = 'No-Show')   AS no_shows,
         round(100.0 * count(*) FILTER (WHERE f.status = 'No-Show')
               / NULLIF(count(*) FILTER (WHERE f.status IN ('Completed','No-Show')), 0), 2) AS no_show_rate_pct,
         coalesce(sum(f.net_amount) FILTER (WHERE f.status = 'Completed'), 0) AS revenue,
         round(avg(f.wait_minutes) FILTER (WHERE f.status = 'Completed'), 1) AS avg_wait_min
  FROM dwh.fact_visits f JOIN dwh.dim_date d USING (date_key)
  GROUP BY d.month_start)
SELECT m.*,
       round(100.0 * (revenue - lag(revenue) OVER w) / NULLIF(lag(revenue) OVER w, 0), 1) AS revenue_mom_pct,
       round(100.0 * (completed_visits - lag(completed_visits) OVER w) / NULLIF(lag(completed_visits) OVER w, 0), 1) AS completed_mom_pct
FROM m WINDOW w AS (ORDER BY month_start);

CREATE VIEW mart.v_department_scorecard AS
WITH s AS (
  SELECT dr.department,
         count(*) AS scheduled_visits,
         count(*) FILTER (WHERE f.status = 'Completed') AS completed_visits,
         round(100.0 * count(*) FILTER (WHERE f.status = 'No-Show')
               / NULLIF(count(*) FILTER (WHERE f.status IN ('Completed','No-Show')), 0), 2) AS no_show_rate_pct,
         coalesce(sum(f.net_amount) FILTER (WHERE f.status = 'Completed'), 0) AS revenue,
         round(avg(f.wait_minutes) FILTER (WHERE f.status = 'Completed'), 1) AS avg_wait_min,
         round((percentile_cont(0.9) WITHIN GROUP (ORDER BY f.wait_minutes))::numeric, 0) AS p90_wait_min,
         round(avg(f.consult_minutes) FILTER (WHERE f.status = 'Completed'), 1) AS avg_consult_min
  FROM dwh.fact_visits f JOIN dwh.dim_doctor dr USING (doctor_key)
  GROUP BY dr.department)
SELECT s.*,
       round(revenue / NULLIF(completed_visits, 0), 0) AS revenue_per_visit,
       round(100.0 * revenue / sum(revenue) OVER (), 1) AS revenue_share_pct,
       rank() OVER (ORDER BY revenue DESC) AS revenue_rank
FROM s;

CREATE VIEW mart.v_doctor_utilization AS
WITH cap AS (
  SELECT month_start, count(*) FILTER (WHERE NOT is_weekend) AS working_days FROM dwh.dim_date GROUP BY month_start),
b AS (
  SELECT d.month_start, f.doctor_key,
         count(*) FILTER (WHERE f.status <> 'Cancelled') AS booked_slots,
         count(*) FILTER (WHERE f.status = 'Completed')  AS completed_visits,
         coalesce(sum(f.consult_minutes) FILTER (WHERE f.status = 'Completed'), 0) / 60.0 AS consult_hours
  FROM dwh.fact_visits f JOIN dwh.dim_date d USING (date_key)
  GROUP BY d.month_start, f.doctor_key)
SELECT b.month_start, dr.doctor_id, dr.full_name AS doctor, dr.department,
       b.booked_slots, b.completed_visits, round(b.consult_hours, 1) AS consult_hours,
       dr.slots_per_day * c.working_days AS capacity_slots,
       round(100.0 * b.booked_slots / (dr.slots_per_day * c.working_days), 1) AS utilization_pct,
       rank() OVER (PARTITION BY b.month_start, dr.department ORDER BY b.completed_visits DESC) AS dept_rank
FROM b JOIN dwh.dim_doctor dr USING (doctor_key) JOIN cap c USING (month_start);

CREATE VIEW mart.v_hourly_heatmap AS
SELECT d.dow, d.dow_name, f.visit_hour, count(*) AS visits,
       round(avg(f.wait_minutes) FILTER (WHERE f.status = 'Completed'), 1) AS avg_wait_min
FROM dwh.fact_visits f JOIN dwh.dim_date d USING (date_key)
WHERE f.status <> 'Cancelled'
GROUP BY d.dow, d.dow_name, f.visit_hour;

CREATE VIEW mart.v_lab_turnaround AS
SELECT t.test_name, t.category, t.target_tat_minutes,
       count(*) AS orders, count(l.resulted_at) AS resulted,
       count(*) FILTER (WHERE l.result_flag = 'Pending') AS pending,
       round(avg(l.turnaround_minutes), 0) AS avg_tat_min,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY l.turnaround_minutes))::numeric, 0) AS p50_tat_min,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY l.turnaround_minutes))::numeric, 0) AS p90_tat_min,
       round(100.0 * count(*) FILTER (WHERE l.turnaround_minutes <= t.target_tat_minutes)
             / NULLIF(count(l.turnaround_minutes), 0), 1) AS pct_within_target
FROM dwh.fact_lab_tests l JOIN dwh.dim_test t USING (test_key)
GROUP BY t.test_name, t.category, t.target_tat_minutes;

-- Turnaround relative to each test's target, by hour the order was placed (finds shift/backlog effects)
CREATE VIEW mart.v_lab_tat_by_hour AS
SELECT extract(hour FROM l.ordered_at)::int AS order_hour, count(*) AS orders,
       round(avg(l.turnaround_minutes::numeric / t.target_tat_minutes), 2) AS avg_tat_to_target_ratio,
       round(100.0 * count(*) FILTER (WHERE l.turnaround_minutes <= t.target_tat_minutes) / count(*), 1) AS pct_within_target
FROM dwh.fact_lab_tests l JOIN dwh.dim_test t USING (test_key)
WHERE l.turnaround_minutes IS NOT NULL
GROUP BY 1;

-- 30-day return rate. Visits in the final 30 days of data are excluded (right-censored: outcome unknowable).
CREATE VIEW mart.v_return_rate AS
WITH c AS (
  SELECT f.patient_key, dr.department, d.full_date AS visit_date,
         lead(d.full_date) OVER (PARTITION BY f.patient_key ORDER BY d.full_date, f.visit_key) AS next_visit_date
  FROM dwh.fact_visits f
  JOIN dwh.dim_date d USING (date_key) JOIN dwh.dim_doctor dr USING (doctor_key)
  WHERE f.status = 'Completed')
SELECT department, date_trunc('month', visit_date)::date AS month_start,
       count(*) AS completed_visits,
       count(*) FILTER (WHERE next_visit_date - visit_date <= 30) AS returned_30d,
       round(100.0 * count(*) FILTER (WHERE next_visit_date - visit_date <= 30) / count(*), 1) AS return_rate_pct
FROM c
WHERE visit_date <= (SELECT max(full_date) FROM dwh.dim_date) - 30
GROUP BY department, date_trunc('month', visit_date);

-- Monthly retention by first-completed-visit cohort (first cohort is left-censored by the data window)
CREATE VIEW mart.v_patient_cohorts AS
WITH v AS (
  SELECT f.patient_key, d.month_start AS m
  FROM dwh.fact_visits f JOIN dwh.dim_date d USING (date_key)
  WHERE f.status = 'Completed' GROUP BY f.patient_key, d.month_start),
fst AS (SELECT patient_key, min(m) AS cohort_month FROM v GROUP BY patient_key),
act AS (
  SELECT fst.cohort_month,
         ((extract(year FROM v.m) - extract(year FROM fst.cohort_month)) * 12
          + extract(month FROM v.m) - extract(month FROM fst.cohort_month))::int AS months_since,
         count(*) AS active_patients
  FROM v JOIN fst USING (patient_key) GROUP BY 1, 2)
SELECT cohort_month, months_since, active_patients,
       round(100.0 * active_patients / first_value(active_patients) OVER (PARTITION BY cohort_month ORDER BY months_since), 1) AS retention_pct
FROM act;

CREATE VIEW mart.v_noshow_drivers AS
WITH base AS (
  SELECT p.insurance_type, p.age_band, f.visit_type, f.status
  FROM dwh.fact_visits f JOIN dwh.dim_patient p USING (patient_key)
  WHERE f.status IN ('Completed','No-Show')),
u AS (
  SELECT 'Insurance' AS dimension, insurance_type AS segment, status FROM base
  UNION ALL SELECT 'Age band', age_band, status FROM base
  UNION ALL SELECT 'Visit type', visit_type, status FROM base)
SELECT dimension, segment, count(*) AS appointments,
       count(*) FILTER (WHERE status = 'No-Show') AS no_shows,
       round(100.0 * count(*) FILTER (WHERE status = 'No-Show') / count(*), 2) AS no_show_rate_pct
FROM u GROUP BY dimension, segment;

-- Executive summary: last 30 days vs the 30 days before (anchored on the latest date in the data)
CREATE VIEW mart.v_exec_summary AS
WITH a AS (SELECT max(full_date) AS mx FROM dwh.dim_date),
p AS (
  SELECT CASE WHEN d.full_date > a.mx - 30 THEN 'cur' ELSE 'prev' END AS period, f.status, f.net_amount, f.wait_minutes
  FROM dwh.fact_visits f JOIN dwh.dim_date d USING (date_key) CROSS JOIN a
  WHERE d.full_date > a.mx - 60),
m AS (
  SELECT period,
         count(*) FILTER (WHERE status = 'Completed') AS completed,
         coalesce(sum(net_amount) FILTER (WHERE status = 'Completed'), 0) AS revenue,
         100.0 * count(*) FILTER (WHERE status = 'No-Show')
           / NULLIF(count(*) FILTER (WHERE status IN ('Completed','No-Show')), 0) AS no_show_rate,
         avg(wait_minutes) FILTER (WHERE status = 'Completed') AS avg_wait
  FROM p GROUP BY period)
SELECT (SELECT mx FROM a) AS as_of_date,
       c.completed AS completed_visits_30d,
       round(100.0 * (c.completed - q.completed) / NULLIF(q.completed, 0), 1) AS completed_change_pct,
       c.revenue AS revenue_30d,
       round(100.0 * (c.revenue - q.revenue) / NULLIF(q.revenue, 0), 1) AS revenue_change_pct,
       round(c.no_show_rate, 2) AS no_show_rate_30d,
       round(c.no_show_rate - q.no_show_rate, 2) AS no_show_change_pts,
       round(c.avg_wait, 1) AS avg_wait_min_30d,
       round(c.avg_wait - q.avg_wait, 1) AS wait_change_min
FROM m c JOIN m q ON c.period = 'cur' AND q.period = 'prev';
