-- Append-only commission accrual ledger, keyed to the event that caused accrual.
BEGIN;

CREATE TABLE IF NOT EXISTS commission_accruals (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_id BIGINT NOT NULL REFERENCES assignments(id),
    lesson_id BIGINT REFERENCES lessons(id),
    event_type VARCHAR(24) NOT NULL CHECK (event_type IN ('lesson', 'threshold', 'subscription', 'closure')),
    amount NUMERIC NOT NULL CHECK (amount >= 0),
    operation_key VARCHAR(128) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_commission_accruals_assignment_id
    ON commission_accruals(assignment_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_commission_accruals_lesson_id
    ON commission_accruals(lesson_id) WHERE lesson_id IS NOT NULL;

-- Backfill the existing aggregate liability at its historical trigger lesson.
WITH ranked_paid_lessons AS (
    SELECT l.id AS lesson_id, l.assignment_id,
           ROW_NUMBER() OVER (PARTITION BY l.assignment_id ORDER BY l.lesson_date, l.id) AS lesson_number
    FROM lessons AS l
    WHERE l.lesson_type = 'paid' AND l.status = 'completed'
), due_assignments AS (
    SELECT a.id AS assignment_id, a.commission_amount,
           ranked.lesson_id
    FROM assignments AS a
    JOIN ranked_paid_lessons AS ranked
      ON ranked.assignment_id = a.id
     AND ranked.lesson_number = a.short_term_lesson_limit
    WHERE a.commission_mode IN ('rate_multiplier', 'fixed', 'manual')
)
INSERT INTO commission_accruals (assignment_id, lesson_id, event_type, amount, operation_key)
SELECT assignment_id, lesson_id, 'threshold', commission_amount,
       'migration:0008:threshold:' || assignment_id::TEXT
FROM due_assignments
WHERE NOT EXISTS (SELECT 1 FROM commission_accruals ca WHERE ca.assignment_id = due_assignments.assignment_id);

INSERT INTO commission_accruals (assignment_id, event_type, amount, operation_key)
SELECT a.id, 'subscription', a.commission_amount, 'migration:0008:subscription:' || a.id::TEXT
FROM assignments AS a
WHERE a.commission_mode = 'subscription'
  AND NOT EXISTS (SELECT 1 FROM commission_accruals ca WHERE ca.assignment_id = a.id);

INSERT INTO commission_accruals (assignment_id, lesson_id, event_type, amount, operation_key)
SELECT a.id, l.id, 'lesson', ROUND(l.amount * a.commission_percentage / 100, 2),
       'migration:0008:percent:' || l.id::TEXT
FROM assignments AS a
JOIN lessons AS l ON l.assignment_id = a.id
WHERE a.commission_mode = 'percent'
  AND l.lesson_type = 'paid' AND l.status = 'completed'
  AND NOT EXISTS (SELECT 1 FROM commission_accruals ca WHERE ca.lesson_id = l.id);

-- A previously closed fixed/manual agreement can be settled before its threshold.
INSERT INTO commission_accruals (assignment_id, event_type, amount, operation_key)
SELECT a.id, 'closure', a.commission_amount, 'migration:0008:closure:' || a.id::TEXT
FROM assignments AS a
WHERE a.is_closed AND a.commission_mode IN ('fixed', 'manual')
  AND NOT EXISTS (SELECT 1 FROM commission_accruals ca WHERE ca.assignment_id = a.id)
  AND NOT EXISTS (SELECT 1 FROM assignment_adjustments aa WHERE aa.assignment_id = a.id);

CREATE OR REPLACE VIEW assignment_finances AS
SELECT a.id AS assignment_id,
       CASE
           WHEN a.is_closed THEN COALESCE(latest.new_amount, accrued.amount)
           ELSE accrued.amount
       END::NUMERIC(12,2) AS commission_amount,
       COALESCE(payments.paid_amount, 0::NUMERIC) AS paid_amount,
       CASE
           WHEN a.is_closed THEN COALESCE(latest.new_amount, accrued.amount)
           ELSE accrued.amount
       END - COALESCE(payments.paid_amount, 0::NUMERIC) AS remaining_amount,
       CASE
           WHEN a.commission_mode = 'percent' THEN accrued.amount
           ELSE a.commission_amount
       END::NUMERIC(12,2) AS agreed_commission
FROM assignments AS a
LEFT JOIN LATERAL (
    SELECT COALESCE(SUM(ca.amount), 0::NUMERIC) AS amount
    FROM commission_accruals AS ca
    WHERE ca.assignment_id = a.id
) AS accrued ON TRUE
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
