-- P1.3: record outcomes so failed exports remain visible and retryable.
BEGIN;

CREATE TABLE IF NOT EXISTS google_sheets_sync_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    succeeded BOOLEAN NOT NULL,
    error_type VARCHAR(128),
    row_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    finished_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_google_sheets_sync_log_finished_at
    ON google_sheets_sync_log (finished_at DESC);

COMMIT;
