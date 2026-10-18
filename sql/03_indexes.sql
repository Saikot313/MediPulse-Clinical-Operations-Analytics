-- Query-driven indexes (each one is justified by a view; see docs/performance.md).
CREATE INDEX IF NOT EXISTS ix_fv_date_status   ON dwh.fact_visits (date_key) INCLUDE (status, net_amount, wait_minutes);
CREATE INDEX IF NOT EXISTS ix_fv_doctor_date   ON dwh.fact_visits (doctor_key, date_key);
CREATE INDEX IF NOT EXISTS ix_fv_patient_comp  ON dwh.fact_visits (patient_key, date_key) INCLUDE (visit_key) WHERE status = 'Completed';
CREATE INDEX IF NOT EXISTS ix_fl_visit         ON dwh.fact_lab_tests (visit_key);
CREATE INDEX IF NOT EXISTS ix_fl_test_tat      ON dwh.fact_lab_tests (test_key) INCLUDE (turnaround_minutes, resulted_at);
