-- Self-submissions from regulated exchanges asking to be added to the
-- register. A submission is a tip, not a listing -- nothing here ever
-- appears on the site until manually verified against the primary
-- regulator source and added to data/exchanges/*.yaml through the normal
-- reviewed git process, same principle as reports but for a much
-- higher-stakes claim (regulatory status, not a user experience).
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  brand_name TEXT NOT NULL,
  website TEXT NOT NULL,
  country TEXT NOT NULL,              -- one of our tracked jurisdiction codes (or MICA)
  legal_entity TEXT,                  -- the entity actually holding the licence, if different from the brand
  licence_reference TEXT,             -- registration/reference number -- the key to verifying against the primary source
  contact_email TEXT NOT NULL,
  notes TEXT,                         -- free text, max 1000 chars (enforced in worker)
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','rejected')),
  ip_hash TEXT                        -- salted hash for rate limiting, never raw IP
);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions (status, created_at);
CREATE INDEX IF NOT EXISTS idx_submissions_iphash ON submissions (ip_hash, created_at);
