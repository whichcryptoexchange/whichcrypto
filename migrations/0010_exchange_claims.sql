-- "Claim your exchange listing" -- lets someone who actually works at a
-- tracked exchange prove control of a contact channel and request the
-- claimed badge shown on that brand's own page. Same discipline as
-- provider_submissions (0006-0008): a claim here is a tip, not a
-- publication -- nothing on the site changes until an admin independently
-- verifies it (domain-match heuristic + email confirmation) and hand-sets
-- `claimed: {status: true}` in data/exchanges/<id>.yaml through the normal
-- reviewed git process. This table -- and claiming in general -- never
-- grants any ability to edit or submit a brand's own regulator-sourced
-- facts (licensing, entities, countries); it only ever unlocks the badge
-- itself, plus being a prerequisite admin checks before adding an
-- affiliate link via /admin/links.
CREATE TABLE IF NOT EXISTS exchange_claims (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exchange_id TEXT NOT NULL,
  brand_name TEXT NOT NULL,        -- snapshot at submission time, for admin display
  website TEXT NOT NULL,           -- snapshot from data/exchanges/*.yaml, for the domain-match heuristic
  contact_name TEXT NOT NULL,
  role TEXT,                       -- e.g. "Compliance", "Marketing", "Founder"
  contact_email TEXT NOT NULL,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  ip_hash TEXT,                    -- salted hash for rate limiting, never raw IP
  token TEXT,                      -- double opt-in email confirmation, same pattern as watchers/digest_subscribers
  email_confirmed INTEGER NOT NULL DEFAULT 0,
  confirmed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_exchange_claims_status ON exchange_claims (status, created_at);
CREATE INDEX IF NOT EXISTS idx_exchange_claims_iphash ON exchange_claims (ip_hash, created_at);
CREATE INDEX IF NOT EXISTS idx_exchange_claims_token ON exchange_claims (token);
