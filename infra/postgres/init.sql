CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

CREATE TABLE IF NOT EXISTS service_bootstrap_check (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    note TEXT
);

INSERT INTO service_bootstrap_check(note)
SELECT 'Fire Forecast database initialized'
WHERE NOT EXISTS (SELECT 1 FROM service_bootstrap_check);
