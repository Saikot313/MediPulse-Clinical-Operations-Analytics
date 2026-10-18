-- BI users read the mart only; they have no access to dwh tables.
REVOKE ALL ON SCHEMA dwh FROM bi_reader;
GRANT USAGE ON SCHEMA mart TO bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO bi_reader;
