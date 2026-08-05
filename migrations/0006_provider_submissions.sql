-- Self-submissions from companies asking for a Technology Provider Profile
-- (the editorial /providers/ section -- companies that are NOT themselves
-- licensed, but rely on a licensed custodian/execution partner). A
-- submission is a tip, not a listing -- nothing here ever appears on the
-- site until the claimed partner relationship is independently verified
-- and a profile is manually authored in data/providers/*.yaml through the
-- normal reviewed git process, same principle as migrations/0005.
CREATE TABLE IF NOT EXISTS provider_submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_name TEXT NOT NULL,
  website TEXT NOT NULL,
  overview TEXT,                       -- what the company does, free text, max 1000 chars (enforced in worker)
  partner_name TEXT NOT NULL,          -- the licensed custodian/execution partner they claim to rely on
  partner_role TEXT,                   -- e.g. "custody", "execution", "both"
  supporting_url TEXT,                 -- evidence of the partnership -- a disclosure page, press release, etc
  contact_email TEXT NOT NULL,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','rejected')),
  ip_hash TEXT                         -- salted hash for rate limiting, never raw IP
);
CREATE INDEX IF NOT EXISTS idx_provider_submissions_status ON provider_submissions (status, created_at);
CREATE INDEX IF NOT EXISTS idx_provider_submissions_iphash ON provider_submissions (ip_hash, created_at);
