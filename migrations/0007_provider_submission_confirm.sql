-- Double opt-in email confirmation for provider submissions, same pattern
-- as watchers/digest_subscribers. Confirming proves control of the contact
-- inbox -- a real identity signal, though still just one input into
-- deciding whether to grant "Claimed Profile" status alongside a backlink
-- check (see data/providers/*.yaml claimed field), not a publication
-- decision on its own.
ALTER TABLE provider_submissions ADD COLUMN token TEXT;
ALTER TABLE provider_submissions ADD COLUMN email_confirmed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE provider_submissions ADD COLUMN confirmed_at TEXT;
CREATE INDEX IF NOT EXISTS idx_provider_submissions_token ON provider_submissions (token);
