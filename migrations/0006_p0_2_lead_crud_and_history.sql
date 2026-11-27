-- P0.2: active tutor flag, concurrency-safe active-name uniqueness,
-- and append-only Lead status history with initial history backfill.
-- Apply only after reviewing duplicates on a test copy.
BEGIN;

ALTER TABLE tutors
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

DO $$
BEGIN
    IF EXISTS (
        SELECT lower(btrim(nickname))
        FROM tutors WHERE is_active
        GROUP BY lower(btrim(nickname)) HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate active tutor names prevent migration 0006';
    END IF;
    IF EXISTS (
        SELECT lower(btrim(nickname))
        FROM clients WHERE is_active
        GROUP BY lower(btrim(nickname)) HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate active client names prevent migration 0006';
    END IF;
    IF EXISTS (
        SELECT lower(btrim(name))
        FROM lead_sources WHERE is_active
        GROUP BY lower(btrim(name)) HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate active lead source names prevent migration 0006';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_tutors_active_nickname_ci
    ON tutors (lower(btrim(nickname))) WHERE is_active;
CREATE UNIQUE INDEX IF NOT EXISTS uq_clients_active_nickname_ci
    ON clients (lower(btrim(nickname))) WHERE is_active;
CREATE UNIQUE INDEX IF NOT EXISTS uq_lead_sources_active_name_ci
    ON lead_sources (lower(btrim(name))) WHERE is_active;

CREATE TABLE IF NOT EXISTS lead_status_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lead_id BIGINT NOT NULL REFERENCES leads(id),
    old_status TEXT CHECK (old_status IS NULL OR old_status IN ('new', 'in_progress', 'assigned', 'lost')),
    new_status TEXT NOT NULL CHECK (new_status IN ('new', 'in_progress', 'assigned', 'lost')),
    reason TEXT,
    changed_by VARCHAR(128) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_lead_status_history_lead_id_id
    ON lead_status_history (lead_id, id);

INSERT INTO lead_status_history (lead_id, old_status, new_status, reason, changed_by)
SELECT l.id, NULL, l.status, COALESCE(l.lost_reason, 'Исторический статус до включения журнала'), 'migration:0006'
FROM leads AS l
WHERE NOT EXISTS (
    SELECT 1 FROM lead_status_history AS h WHERE h.lead_id = l.id
);

COMMIT;
