-- Outreach Tracker mirror. Sheet stays the operational source of truth;
-- Postgres is the durable copy for history and queries.

CREATE TABLE IF NOT EXISTS leads (
    lead_id TEXT PRIMARY KEY,
    spreadsheet_id TEXT NOT NULL,
    worksheet TEXT NOT NULL DEFAULT 'Outreach Tracker',
    row_number INTEGER,
    research_status TEXT,
    outreach_status TEXT,
    assigned_sender TEXT,
    company_name TEXT,
    contact_first_name TEXT,
    contact_email TEXT,
    industry TEXT,
    verified_trigger TEXT,
    workflow_handoff TEXT,
    short_workflow_topic TEXT,
    subject_line TEXT,
    day0_email TEXT,
    day4_email TEXT,
    day8_email TEXT,
    day14_email TEXT,
    message_id TEXT,
    last_action_date DATE,
    next_action_date DATE,
    notes TEXT,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS leads_status_idx ON leads (outreach_status);
CREATE INDEX IF NOT EXISTS leads_next_action_idx ON leads (next_action_date);
CREATE INDEX IF NOT EXISTS leads_email_idx ON leads (contact_email);

CREATE TABLE IF NOT EXISTS send_events (
    id BIGSERIAL PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads (lead_id) ON DELETE CASCADE,
    touch TEXT NOT NULL,
    mailbox TEXT NOT NULL,
    message_id TEXT,
    parent_message_id TEXT,
    to_email TEXT,
    subject TEXT,
    sent_at TIMESTAMPTZ,
    smtp_ok BOOLEAN NOT NULL DEFAULT FALSE,
    sheet_synced BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (lead_id, touch)
);

CREATE INDEX IF NOT EXISTS send_events_mailbox_sent_idx ON send_events (mailbox, sent_at);
