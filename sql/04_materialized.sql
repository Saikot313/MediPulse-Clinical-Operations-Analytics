-- Heavy window-function views are materialised; `medipulse refresh` rebuilds them after each load.
CREATE MATERIALIZED VIEW mart.mv_return_rate    AS SELECT * FROM mart.v_return_rate;
CREATE UNIQUE INDEX uq_mv_return_rate ON mart.mv_return_rate (department, month_start);
CREATE MATERIALIZED VIEW mart.mv_patient_cohorts AS SELECT * FROM mart.v_patient_cohorts;
CREATE UNIQUE INDEX uq_mv_cohorts ON mart.mv_patient_cohorts (cohort_month, months_since);
