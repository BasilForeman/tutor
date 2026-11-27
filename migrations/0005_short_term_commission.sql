-- Store the agreed rate multiplier and settlement history. 4 lessons is the
-- default short-term limit; closing an Assignment after <= limit settles at 25%
-- of actual paid/completed lesson earnings. Apply after migrations 0001-0004.
BEGIN;

ALTER TABLE assignments
    ADD COLUMN IF NOT EXISTS commission_multiplier NUMERIC,
    ADD COLUMN IF NOT EXISTS short_term_lesson_limit BIGINT NOT NULL DEFAULT 4,
    ADD COLUMN IF NOT EXISTS is_closed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS closed_by TEXT,
    ADD COLUMN IF NOT EXISTS close_reason TEXT,
    ADD COLUMN IF NOT EXISTS close_operation_key VARCHAR(128);

UPDATE assignments
SET commission_multiplier = CASE
    WHEN rate > 0 AND commission_amount > 0 THEN commission_amount / rate
    ELSE 4
END
WHERE commission_multiplier IS NULL;

ALTER TABLE assignments
    ALTER COLUMN commission_multiplier SET DEFAULT 4,
    ALTER COLUMN commission_multiplier SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_assignments_multiplier_positive' AND conrelid = 'assignments'::regclass) THEN
        ALTER TABLE assignments ADD CONSTRAINT ck_assignments_multiplier_positive CHECK (commission_multiplier > 0) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_assignments_short_term_limit_positive' AND conrelid = 'assignments'::regclass) THEN
        ALTER TABLE assignments ADD CONSTRAINT ck_assignments_short_term_limit_positive CHECK (short_term_lesson_limit > 0) NOT VALID;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_assignments_close_operation_key
    ON assignments(close_operation_key) WHERE close_operation_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS assignment_adjustments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_id BIGINT NOT NULL REFERENCES assignments(id),
    previous_amount NUMERIC NOT NULL CHECK (previous_amount >= 0),
    new_amount NUMERIC NOT NULL CHECK (new_amount >= 0),
    difference NUMERIC NOT NULL,
    reason TEXT NOT NULL,
    author TEXT NOT NULL,
    operation_key VARCHAR(128) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_assignment_adjustments_assignment_id
    ON assignment_adjustments(assignment_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_adjustments_operation_key
    ON assignment_adjustments(operation_key);

-- PostgreSQL cannot change an existing view column type with CREATE OR REPLACE.
-- Migration 0001 made this relation a derived view (any legacy table was kept
-- under assignment_finances_legacy_0001), so dropping only the view is safe.
DROP VIEW IF EXISTS assignment_finances;

CREATE VIEW assignment_finances AS
SELECT a.id AS assignment_id,
       CASE
           WHEN a.is_closed THEN COALESCE(latest.new_amount, a.commission_amount)
           WHEN lessons.paid_count >= a.short_term_lesson_limit THEN a.commission_amount
           ELSE 0::NUMERIC
       END::NUMERIC(12,2) AS commission_amount,
       COALESCE(payments.paid_amount, 0::NUMERIC) AS paid_amount,
       CASE
           WHEN a.is_closed THEN COALESCE(latest.new_amount, a.commission_amount)
           WHEN lessons.paid_count >= a.short_term_lesson_limit THEN a.commission_amount
           ELSE 0::NUMERIC
       END - COALESCE(payments.paid_amount, 0::NUMERIC) AS remaining_amount,
       a.commission_amount AS agreed_commission
FROM assignments AS a
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS paid_count
    FROM lessons AS l
    WHERE l.assignment_id = a.id
      AND l.lesson_type = 'paid'
      AND l.status = 'completed'
) AS lessons ON TRUE
LEFT JOIN LATERAL (
    SELECT SUM(p.amount) AS paid_amount
    FROM payments AS p
    WHERE p.assignment_id = a.id
) AS payments ON TRUE
LEFT JOIN LATERAL (
    SELECT aa.new_amount
    FROM assignment_adjustments AS aa
    WHERE aa.assignment_id = a.id
    ORDER BY aa.id DESC
    LIMIT 1
) AS latest ON TRUE;

COMMIT;
