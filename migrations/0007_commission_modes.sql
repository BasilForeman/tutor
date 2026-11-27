-- P0.4: snapshot the agreed commission mode; subscriptions accrue immediately.
-- Other modes retain the existing lesson threshold until their rules are configured.
BEGIN;

ALTER TABLE assignments
    ADD COLUMN IF NOT EXISTS commission_mode VARCHAR(24) NOT NULL DEFAULT 'rate_multiplier',
    ADD COLUMN IF NOT EXISTS commission_percentage NUMERIC,
    ADD COLUMN IF NOT EXISTS subscription_purchase_date DATE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_assignments_commission_mode'
          AND conrelid = 'assignments'::regclass
    ) THEN
        ALTER TABLE assignments ADD CONSTRAINT ck_assignments_commission_mode
            CHECK (commission_mode IN ('rate_multiplier', 'fixed', 'manual', 'subscription', 'percent')) NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_assignments_subscription_purchase_date'
          AND conrelid = 'assignments'::regclass
    ) THEN
        ALTER TABLE assignments ADD CONSTRAINT ck_assignments_subscription_purchase_date
            CHECK (commission_mode <> 'subscription' OR subscription_purchase_date IS NOT NULL) NOT VALID;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_assignments_commission_percentage'
          AND conrelid = 'assignments'::regclass
    ) THEN
        ALTER TABLE assignments ADD CONSTRAINT ck_assignments_commission_percentage
            CHECK (commission_mode <> 'percent' OR (commission_percentage > 0 AND commission_percentage <= 100)) NOT VALID;
    END IF;
END $$;

-- This revision narrows agreed_commission to NUMERIC(12,2); PostgreSQL does
-- not allow CREATE OR REPLACE VIEW to alter an existing output column type.
DROP VIEW IF EXISTS assignment_finances;

CREATE VIEW assignment_finances AS
SELECT a.id AS assignment_id,
       CASE
           WHEN a.is_closed THEN COALESCE(latest.new_amount, a.commission_amount)
           WHEN a.commission_mode = 'subscription' THEN a.commission_amount
           WHEN a.commission_mode = 'percent' THEN COALESCE(percent_earnings.amount * a.commission_percentage / 100, 0::NUMERIC)
           WHEN lessons.paid_count >= a.short_term_lesson_limit THEN a.commission_amount
           ELSE 0::NUMERIC
       END::NUMERIC(12,2) AS commission_amount,
       COALESCE(payments.paid_amount, 0::NUMERIC) AS paid_amount,
       CASE
           WHEN a.is_closed THEN COALESCE(latest.new_amount, a.commission_amount)
           WHEN a.commission_mode = 'subscription' THEN a.commission_amount
           WHEN a.commission_mode = 'percent' THEN COALESCE(percent_earnings.amount * a.commission_percentage / 100, 0::NUMERIC)
           WHEN lessons.paid_count >= a.short_term_lesson_limit THEN a.commission_amount
           ELSE 0::NUMERIC
       END - COALESCE(payments.paid_amount, 0::NUMERIC) AS remaining_amount,
       CASE
           WHEN a.commission_mode = 'percent' THEN COALESCE(percent_earnings.amount * a.commission_percentage / 100, 0::NUMERIC)
           ELSE a.commission_amount
       END::NUMERIC(12,2) AS agreed_commission
FROM assignments AS a
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS paid_count
    FROM lessons AS l
    WHERE l.assignment_id = a.id
      AND l.lesson_type = 'paid'
      AND l.status = 'completed'
) AS lessons ON TRUE
LEFT JOIN LATERAL (
    SELECT COALESCE(SUM(l.amount), 0::NUMERIC) AS amount
    FROM lessons AS l
    WHERE l.assignment_id = a.id
      AND l.lesson_type = 'paid'
      AND l.status = 'completed'
) AS percent_earnings ON TRUE
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
