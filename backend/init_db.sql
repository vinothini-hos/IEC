-- Reference schema. In practice, app/main.py auto-creates these tables via
-- SQLAlchemy's Base.metadata.create_all() on startup - this file is here
-- for manual setup / documentation / migrating away from create_all later.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE direction_enum AS ENUM ('incoming', 'outgoing');

CREATE TABLE threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    gmail_thread_id VARCHAR UNIQUE NOT NULL,
    subject VARCHAR NOT NULL DEFAULT '',
    participants TEXT DEFAULT '',
    last_message_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_threads_gmail_thread_id ON threads (gmail_thread_id);

CREATE TABLE emails (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    gmail_message_id VARCHAR UNIQUE,
    direction direction_enum NOT NULL,
    sender VARCHAR NOT NULL,
    recipient VARCHAR NOT NULL,
    cc VARCHAR DEFAULT '',
    subject VARCHAR DEFAULT '',
    snippet VARCHAR DEFAULT '',
    body_text TEXT DEFAULT '',
    body_html TEXT,
    sent_at TIMESTAMPTZ DEFAULT now(),
    is_read BOOLEAN DEFAULT false
);
CREATE INDEX idx_emails_thread_id ON emails (thread_id);
CREATE INDEX idx_emails_gmail_message_id ON emails (gmail_message_id);

CREATE TABLE attachments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email_id UUID NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    filename VARCHAR NOT NULL,
    mime_type VARCHAR DEFAULT 'application/octet-stream',
    size_bytes INTEGER DEFAULT 0,
    gmail_attachment_id VARCHAR,
    local_path VARCHAR
);
CREATE INDEX idx_attachments_email_id ON attachments (email_id);
