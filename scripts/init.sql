-- MPMB Copilot Database Schema
-- PostgreSQL 16+ with JSONB support

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Sessions Table (Conversations)
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL DEFAULT 'New Conversation',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- User identification (optional for now, add when auth is implemented)
    user_id VARCHAR(255),

    -- Session settings stored as JSONB for flexibility
    settings JSONB DEFAULT '{
        "model": "claude-sonnet-4-20250514",
        "provider": "anthropic",
        "temperature": 0.2,
        "max_tokens": 4000,
        "tools_enabled": ["web_search", "rag"],
        "rag_settings": {
            "top_k": 5,
            "similarity_threshold": 0.7
        }
    }'::jsonb,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Soft delete
    deleted_at TIMESTAMP WITH TIME ZONE,

    -- Indexes
    CONSTRAINT sessions_title_length CHECK (char_length(title) >= 1)
);

-- Create indexes for sessions
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sessions_deleted_at ON sessions(deleted_at) WHERE deleted_at IS NULL;

-- Messages Table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,

    -- Message role: 'user', 'assistant', 'system'
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),

    -- Message content stored as JSONB to support multi-modal content
    -- Examples:
    -- Simple text: {"type": "text", "text": "How do I add a spell?"}
    -- Code: {"type": "code", "language": "javascript", "code": "var spell = {...}"}
    -- Image: {"type": "image", "url": "/uploads/image.png", "alt": "Screenshot"}
    -- Multi-part: [{"type": "text", "text": "..."}, {"type": "code", "code": "..."}]
    content JSONB NOT NULL,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- LLM Provider Tracking
    provider VARCHAR(50),           -- 'anthropic', 'openai', 'ollama'
    model VARCHAR(100),              -- 'claude-sonnet-4-20250514', 'gpt-4', etc.

    -- Token Usage Tracking
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,

    -- Performance Tracking
    latency_ms INTEGER,              -- Response time in milliseconds
    stop_reason VARCHAR(50),         -- 'end_turn', 'max_tokens', 'stop_sequence', etc.

    -- Metadata: retrieved documents, tool calls, streaming state, etc.
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Message sequence within session
    sequence_number INTEGER NOT NULL,

    CONSTRAINT messages_sequence_unique UNIQUE (session_id, sequence_number)
);

-- Create indexes for messages
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_messages_sequence ON messages(session_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_messages_provider ON messages(provider);
CREATE INDEX IF NOT EXISTS idx_messages_model ON messages(model);

-- GIN index for JSONB content search
CREATE INDEX IF NOT EXISTS idx_messages_content_gin ON messages USING gin(content);
CREATE INDEX IF NOT EXISTS idx_messages_metadata_gin ON messages USING gin(metadata);

-- Files Table (for uploaded files)
CREATE TABLE IF NOT EXISTS files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id UUID REFERENCES messages(id) ON DELETE CASCADE,

    -- File information
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    file_size BIGINT NOT NULL,

    -- File hash for deduplication
    file_hash VARCHAR(64),

    -- Timestamps
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    CONSTRAINT files_size_positive CHECK (file_size > 0)
);

-- Create indexes for files
CREATE INDEX IF NOT EXISTS idx_files_session_id ON files(session_id);
CREATE INDEX IF NOT EXISTS idx_files_message_id ON files(message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_files_uploaded_at ON files(uploaded_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash) WHERE file_hash IS NOT NULL;

-- Document Chunks Table (for RAG context tracking)
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Source information
    source_file VARCHAR(512) NOT NULL,
    chunk_index INTEGER NOT NULL,

    -- Content
    content TEXT NOT NULL,

    -- Qdrant reference
    qdrant_id VARCHAR(255) UNIQUE,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    indexed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT doc_chunks_source_index_unique UNIQUE (source_file, chunk_index)
);

-- Create indexes for document chunks
CREATE INDEX IF NOT EXISTS idx_doc_chunks_source ON document_chunks(source_file);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_qdrant_id ON document_chunks(qdrant_id) WHERE qdrant_id IS NOT NULL;

-- This table links messages to the document chunks that were used to generate them
CREATE TABLE IF NOT EXISTS message_retrievals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    document_chunk_id UUID NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,

    -- Retrieval metadata
    rank INTEGER NOT NULL,           -- Order in which chunk was retrieved (1 = most relevant)
    score FLOAT NOT NULL,            -- Similarity score from vector search
    snippet TEXT,                    -- Optional: exact text snippet shown to user

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT message_retrievals_unique UNIQUE (message_id, document_chunk_id)
);

-- Indexes for message_retrievals
CREATE INDEX IF NOT EXISTS idx_msg_retrievals_message ON message_retrievals(message_id);
CREATE INDEX IF NOT EXISTS idx_msg_retrievals_chunk ON message_retrievals(document_chunk_id);
CREATE INDEX IF NOT EXISTS idx_msg_retrievals_score ON message_retrievals(score DESC);
CREATE INDEX IF NOT EXISTS idx_msg_retrievals_rank ON message_retrievals(rank);

-- Usage/Analytics Table (optional, for tracking)
CREATE TABLE IF NOT EXISTS usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,

    -- Event information
    event_type VARCHAR(50) NOT NULL,

    -- Details stored as JSONB
    event_data JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for usage logs
CREATE INDEX IF NOT EXISTS idx_usage_logs_created_at ON usage_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_logs_session_id ON usage_logs(session_id) WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_usage_logs_event_type ON usage_logs(event_type);

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for sessions updated_at
CREATE TRIGGER sessions_updated_at_trigger
    BEFORE UPDATE ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to auto-increment sequence_number
CREATE OR REPLACE FUNCTION set_message_sequence_number()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.sequence_number IS NULL THEN
        SELECT COALESCE(MAX(sequence_number), 0) + 1
        INTO NEW.sequence_number
        FROM messages
        WHERE session_id = NEW.sequence_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for auto-incrementing message sequence
CREATE TRIGGER messages_sequence_trigger
    BEFORE INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION set_message_sequence_number();

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO mpmb_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO mpmb_user;
