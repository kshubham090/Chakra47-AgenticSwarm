-- Run this in your Supabase SQL Editor before starting the framework.
-- This creates the audit_logs table used by AuditChain.

CREATE TABLE IF NOT EXISTS audit_logs (
    id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    task_id          TEXT        NOT NULL,
    agent            TEXT        NOT NULL,
    status           TEXT        NOT NULL,        -- PASS | BLOCK | ESCALATE | EXCEPTION
    decision_source  TEXT        NOT NULL,        -- code | llm
    reason           TEXT        DEFAULT '',
    input_hash       TEXT        NOT NULL,        -- SHA-256 of raw input
    prev_hash        TEXT        NOT NULL,        -- SHA-256 of previous block (genesis = 0*64)
    block_hash       TEXT        NOT NULL,        -- SHA-256 of this block
    extra_payload    JSONB       DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Efficient chain verification and task-scoped queries
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (created_at ASC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_task_id    ON audit_logs (task_id);

-- Row Level Security: only service role can read/write audit logs
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_only" ON audit_logs
    USING (auth.role() = 'service_role');
