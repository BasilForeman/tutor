-- Create a lesson log with explicit type/status and retry protection.
-- Apply after 0001 and 0002 on an inspected test database.
BEGIN;

CREATE TABLE IF NOT EXISTS lessons (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_id BIGINT NOT NULL REFERENCES assignments(id),
    lesson_date DATE NOT NULL,
    lesson_type VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    amount NUMERIC,
    notes TEXT,
    operation_key VARCHAR(128),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_lessons_type CHECK (lesson_type IN ('trial', 'paid')),
    CONSTRAINT ck_lessons_status CHECK (status IN ('completed', 'cancelled')),
    CONSTRAINT ck_lessons_amount_nonnegative CHECK (amount IS NULL OR amount >= 0),
    CONSTRAINT ck_lessons_trial_free CHECK (lesson_type <> 'trial' OR amount IS NULL OR amount = 0),
    CONSTRAINT ck_lessons_completed_paid_amount CHECK (status <> 'completed' OR lesson_type <> 'paid' OR amount > 0)
);

CREATE INDEX IF NOT EXISTS ix_lessons_assignment_id ON lessons(assignment_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_lessons_operation_key
    ON lessons(operation_key) WHERE operation_key IS NOT NULL;

COMMIT;
