-- Store one real remittance and retain per-assignment payment allocations.
-- Existing payments are preserved and backfilled one-to-one.
BEGIN;

CREATE TABLE IF NOT EXISTS payment_batches (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tutor_id BIGINT NOT NULL REFERENCES tutors(id),
    payment_date DATE NOT NULL,
    amount NUMERIC NOT NULL CHECK (amount > 0),
    notes TEXT,
    operation_key VARCHAR(128) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_payment_batches_tutor_id ON payment_batches(tutor_id);
CREATE INDEX IF NOT EXISTS ix_payment_batches_payment_date ON payment_batches(payment_date);

ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_batch_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_payments_payment_batch_id'
          AND conrelid = 'payments'::regclass
    ) THEN
        ALTER TABLE payments ADD CONSTRAINT fk_payments_payment_batch_id
            FOREIGN KEY (payment_batch_id) REFERENCES payment_batches(id) NOT VALID;
    END IF;
END $$;

-- Preserve each existing payment row as its own historical receipt.
INSERT INTO payment_batches (tutor_id, payment_date, amount, notes, operation_key, created_at)
SELECT a.tutor_id, p.payment_date, p.amount, p.notes,
       'legacy-payment:' || p.id::text, COALESCE(p.created_at, CURRENT_TIMESTAMP)
FROM payments p
JOIN assignments a ON a.id = p.assignment_id
WHERE p.payment_batch_id IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM payment_batches b
      WHERE b.operation_key = 'legacy-payment:' || p.id::text
  );

UPDATE payments p
SET payment_batch_id = b.id
FROM payment_batches b
WHERE p.payment_batch_id IS NULL
  AND b.operation_key = 'legacy-payment:' || p.id::text;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM payments WHERE payment_batch_id IS NULL) THEN
        RAISE EXCEPTION 'Migration 0013 could not link every payment to a batch';
    END IF;
END $$;

ALTER TABLE payments ALTER COLUMN payment_batch_id SET NOT NULL;
ALTER TABLE payments VALIDATE CONSTRAINT fk_payments_payment_batch_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_batch_assignment
    ON payments(payment_batch_id, assignment_id);
CREATE INDEX IF NOT EXISTS ix_payments_payment_batch_id ON payments(payment_batch_id);

COMMIT;
