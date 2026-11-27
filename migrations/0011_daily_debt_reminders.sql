-- Persist one debt reminder per administrator and local calendar day.
BEGIN;

CREATE TABLE IF NOT EXISTS debt_reminder_log (
    admin_id BIGINT NOT NULL,
    reminder_date DATE NOT NULL,
    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (admin_id, reminder_date)
);

COMMIT;
