-- Permit append-only allocations from an already received tutor payment.
-- The service locks the parent batch and ensures total allocations never exceed it.
BEGIN;

DROP INDEX IF EXISTS uq_payments_batch_assignment;
CREATE INDEX IF NOT EXISTS ix_payments_batch_assignment
    ON payments(payment_batch_id, assignment_id);

COMMIT;
