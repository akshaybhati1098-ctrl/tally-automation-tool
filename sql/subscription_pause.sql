-- Subscription pause metadata
-- Safe to run on existing PostgreSQL databases.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS subscription_paused_at TIMESTAMP;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS subscription_pause_remaining_seconds BIGINT;
