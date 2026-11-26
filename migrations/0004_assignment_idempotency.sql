-- Protect repeat delivery of the same assignment operation while allowing
-- separate Assignment records for intentional reassignments.
BEGIN;

ALTER TABLE assignments
    ADD COLUMN IF NOT EXISTS operation_key VARCHAR(128);

CREATE UNIQUE INDEX IF NOT EXISTS uq_assignments_operation_key
    ON assignments(operation_key)
    WHERE operation_key IS NOT NULL;

COMMIT;
