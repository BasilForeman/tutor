-- Tutor CRM schema migration 0001.
-- Review the target database and take a backup before use.
-- Explicitly apply to a confirmed local/test database; never run on production
-- without a reviewed backup and a separate approval.
BEGIN;

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS contact TEXT,
    ADD COLUMN IF NOT EXISTS notes TEXT,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE lead_sources
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS leads (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id BIGINT NOT NULL REFERENCES clients(id),
    source_id BIGINT NOT NULL REFERENCES lead_sources(id),
    subject TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'in_progress', 'assigned', 'lost')),
    lost_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE assignments
    ADD COLUMN IF NOT EXISTS lead_id BIGINT;

-- Preserve legacy assignments by making one historical lead per old assignment.
-- Marker is stable within this transaction, so the UPDATE can link each row.
INSERT INTO leads (client_id, source_id, subject, notes, status, created_at)
SELECT a.client_id,
       a.source_id,
       '__legacy_assignment_' || a.id::TEXT,
       'Создано миграцией 0001 для сохранения исходной передачи',
       'assigned',
       COALESCE(a.created_at, CURRENT_TIMESTAMP)
FROM assignments AS a
WHERE a.lead_id IS NULL;

UPDATE assignments AS a
SET lead_id = l.id
FROM leads AS l
WHERE a.lead_id IS NULL
  AND l.client_id = a.client_id
  AND l.source_id = a.source_id
  AND l.subject = '__legacy_assignment_' || a.id::TEXT;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM assignments WHERE lead_id IS NULL) THEN
        RAISE EXCEPTION 'Migration 0001 could not link all assignments to leads';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_assignments_lead_id_leads'
          AND conrelid = 'assignments'::regclass
    ) THEN
        ALTER TABLE assignments
            ADD CONSTRAINT fk_assignments_lead_id_leads
            FOREIGN KEY (lead_id) REFERENCES leads(id);
    END IF;
END $$;

ALTER TABLE assignments ALTER COLUMN lead_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_assignments_lead_id ON assignments(lead_id);
CREATE INDEX IF NOT EXISTS ix_leads_status_created_at ON leads(status, created_at);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_assignments_rate_positive' AND conrelid = 'assignments'::regclass) THEN
        ALTER TABLE assignments ADD CONSTRAINT ck_assignments_rate_positive CHECK (rate > 0) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_assignments_commission_nonnegative' AND conrelid = 'assignments'::regclass) THEN
        ALTER TABLE assignments ADD CONSTRAINT ck_assignments_commission_nonnegative CHECK (commission_amount >= 0) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_payments_amount_positive' AND conrelid = 'payments'::regclass) THEN
        ALTER TABLE payments ADD CONSTRAINT ck_payments_amount_positive CHECK (amount > 0) NOT VALID;
    END IF;
END $$;

-- Keep a legacy aggregate table intact if an earlier create_all created it.
-- The application-facing relation becomes a view computed from assignments/payments.
DO $$
DECLARE relation_kind "char";
BEGIN
    SELECT c.relkind INTO relation_kind
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = 'assignment_finances';

    IF relation_kind = 'r' THEN
        IF to_regclass('public.assignment_finances_legacy_0001') IS NOT NULL THEN
            RAISE EXCEPTION 'assignment_finances_legacy_0001 already exists; inspect schema before migration';
        END IF;
        ALTER TABLE assignment_finances RENAME TO assignment_finances_legacy_0001;
    ELSIF relation_kind = 'm' THEN
        IF to_regclass('public.assignment_finances_legacy_0001') IS NOT NULL THEN
            RAISE EXCEPTION 'assignment_finances_legacy_0001 already exists; inspect schema before migration';
        END IF;
        ALTER MATERIALIZED VIEW assignment_finances RENAME TO assignment_finances_legacy_0001;
    ELSIF relation_kind IS NOT NULL AND relation_kind <> 'v' THEN
        RAISE EXCEPTION 'Unexpected assignment_finances relation type (%); inspect schema before migration', relation_kind;
    END IF;
END $$;

CREATE OR REPLACE VIEW assignment_finances AS
SELECT a.id AS assignment_id,
       a.commission_amount,
       COALESCE(SUM(p.amount), 0::NUMERIC) AS paid_amount,
       a.commission_amount - COALESCE(SUM(p.amount), 0::NUMERIC) AS remaining_amount
FROM assignments AS a
LEFT JOIN payments AS p ON p.assignment_id = a.id
GROUP BY a.id, a.commission_amount;

COMMIT;
