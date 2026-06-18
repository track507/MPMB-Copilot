-- Migration 001: message_feedback table (answer feedback).
-- Idempotent. For existing databases whose volume predates this table
-- Apply (PowerShell):
--   Get-Content docker/postgres/migrations/001_message_feedback.sql -Raw | docker compose exec -T postgres psql -U mpmb_user -d mpmb_copilot
-- Apply (bash):
--   docker compose exec -T postgres psql -U "${POSTGRES_USER:-mpmb_user}" -d "${POSTGRES_DB:-mpmb_copilot}" < docker/postgres/migrations/001_message_feedback.sql

CREATE TABLE IF NOT EXISTS message_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    message_id UUID NOT NULL UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
    rating VARCHAR(10) NOT NULL CHECK (rating IN ('up', 'down')),
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_message_feedback_message ON message_feedback(message_id);
CREATE INDEX IF NOT EXISTS idx_message_feedback_rating ON message_feedback(rating);

DROP TRIGGER IF EXISTS message_feedback_updated_at_trigger ON message_feedback;
CREATE TRIGGER message_feedback_updated_at_trigger
    BEFORE UPDATE ON message_feedback
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
