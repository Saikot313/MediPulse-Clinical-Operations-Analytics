-- MediPulse star schema (rebuilds from scratch). Conformed names follow MediFlow's dwh/mart layout.
DROP SCHEMA IF EXISTS mart CASCADE;
DROP SCHEMA IF EXISTS dwh CASCADE;
CREATE SCHEMA dwh;
CREATE SCHEMA mart;

DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bi_reader') THEN
    CREATE ROLE bi_reader LOGIN PASSWORD 'bi_reader';
  END IF;
END $$;

CREATE TABLE dwh.dim_date (
  date_key int PRIMARY KEY, full_date date UNIQUE NOT NULL, year smallint, quarter smallint, month smallint,
  month_name text, month_start date NOT NULL, iso_week smallint, dow smallint, dow_name text, is_weekend boolean
);
CREATE TABLE dwh.dim_doctor (
  doctor_key int PRIMARY KEY, doctor_id text UNIQUE NOT NULL, full_name text, department text NOT NULL,
  slots_per_day smallint NOT NULL CHECK (slots_per_day > 0)
);
CREATE TABLE dwh.dim_patient (  -- pseudonymous: no name, no date of birth
  patient_key int PRIMARY KEY, patient_token text UNIQUE NOT NULL, age_band text, gender text, city text, insurance_type text
);
CREATE TABLE dwh.dim_test (
  test_key int PRIMARY KEY, test_name text UNIQUE NOT NULL, category text, target_tat_minutes int NOT NULL
);
CREATE TABLE dwh.fact_visits (  -- grain: one row per scheduled visit
  visit_key int PRIMARY KEY, visit_id text UNIQUE NOT NULL,
  date_key int NOT NULL REFERENCES dwh.dim_date, patient_key int NOT NULL REFERENCES dwh.dim_patient,
  doctor_key int NOT NULL REFERENCES dwh.dim_doctor, visit_hour smallint CHECK (visit_hour BETWEEN 0 AND 23),
  visit_type text CHECK (visit_type IN ('New','Follow-up','Emergency')),
  status text NOT NULL CHECK (status IN ('Completed','No-Show','Cancelled')),
  wait_minutes int, consult_minutes int,
  consultation_fee numeric(10,2) NOT NULL, discount numeric(10,2) NOT NULL, net_amount numeric(10,2) NOT NULL,
  CHECK (net_amount = consultation_fee - discount)
);
CREATE TABLE dwh.fact_lab_tests (  -- grain: one row per lab order
  lab_key int PRIMARY KEY, lab_order_id text UNIQUE NOT NULL,
  visit_key int NOT NULL REFERENCES dwh.fact_visits, test_key int NOT NULL REFERENCES dwh.dim_test,
  ordered_at timestamp NOT NULL, resulted_at timestamp, turnaround_minutes int,
  result_flag text CHECK (result_flag IN ('Normal','High','Low','Pending'))
);
