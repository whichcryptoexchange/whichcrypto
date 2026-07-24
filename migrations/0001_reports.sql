-- User reports: the proprietary data layer. Nothing publishes without review.
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exchange_id TEXT NOT NULL,
  country TEXT NOT NULL,              -- ISO 3166-1 alpha-2
  outcome TEXT NOT NULL CHECK (outcome IN (
    'signup_ok','signup_blocked','kyc_blocked',
    'withdrawal_ok','withdrawal_delayed','withdrawal_refused',
    'account_closed','geo_blocked'
  )),
  detail TEXT,                        -- free text, max 1000 chars (enforced in worker)
  occurred_on TEXT,                   -- optional YYYY-MM-DD from user
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','rejected')),
  ip_hash TEXT                        -- salted hash for rate limiting, never raw IP
);
CREATE INDEX IF NOT EXISTS idx_reports_exchange ON reports (exchange_id, status);
CREATE INDEX IF NOT EXISTS idx_reports_iphash ON reports (ip_hash, created_at);
