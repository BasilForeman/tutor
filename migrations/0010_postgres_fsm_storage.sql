-- Persist Telegram FSM state/data across bot restarts.
BEGIN;

CREATE TABLE IF NOT EXISTS fsm_states (
    bot_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    thread_id BIGINT NOT NULL DEFAULT 0,
    business_connection_id VARCHAR(128) NOT NULL DEFAULT '',
    destiny VARCHAR(64) NOT NULL,
    state VARCHAR(128),
    data JSONB NOT NULL DEFAULT '{}'::JSONB,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bot_id, chat_id, user_id, thread_id, business_connection_id, destiny)
);

CREATE INDEX IF NOT EXISTS ix_fsm_states_updated_at ON fsm_states(updated_at);

COMMIT;
