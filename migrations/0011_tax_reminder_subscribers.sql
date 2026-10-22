-- UK crypto tax deadline reminders + occasional "rules changed" alerts --
-- a separate list from digest_subscribers (0004): different content,
-- different cadence/triggers (calendar-driven + manual ad-hoc vs. weekly
-- regulatory diff), someone may want one without the other. Same double
-- opt-in mechanism and reasoning as digest_subscribers/watchers.
CREATE TABLE IF NOT EXISTS tax_reminder_subscribers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  token TEXT NOT NULL UNIQUE,
  confirmed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  confirmed_at TEXT,
  ip_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_tax_reminder_subscribers_token ON tax_reminder_subscribers(token);
