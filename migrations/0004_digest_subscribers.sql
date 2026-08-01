-- Weekly roundup email subscribers -- everything that changed across the
-- whole register, not tied to one brand (see watchers for that). Same
-- double opt-in mechanism and reasoning as watchers.
CREATE TABLE IF NOT EXISTS digest_subscribers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  token TEXT NOT NULL UNIQUE,
  confirmed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  confirmed_at TEXT,
  ip_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_digest_subscribers_token ON digest_subscribers(token);
