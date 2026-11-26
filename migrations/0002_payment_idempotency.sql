-- Add a stable operation key so webhook/update retries cannot duplicate payments.
-- Apply only after the database backup and local/test migration of 0001.
BEGIN;

ALTER TABLE payments
    ADD COLUMN IF NOT EXISTS operation_key VARCHAR(128);

CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_operation_key
    ON payments(operation_key)
    WHERE operation_key IS NOT NULL;

COMMIT;
