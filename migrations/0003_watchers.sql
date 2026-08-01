-- "Watch this exchange" email alerts. Double opt-in: a row exists
-- unconfirmed from the moment someone submits the signup form, and only
-- becomes real (i.e. eligible to receive change notifications) once the
-- confirmation link sent to that email address is clicked. This is both
-- the anti-spam-signup mechanism and the GDPR consent record in one --
-- nobody can be signed up to receive email without clicking a link sent
-- to their own inbox.
CREATE TABLE IF NOT EXISTS watchers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exchange_id TEXT NOT NULL,
  email TEXT NOT NULL,
  token TEXT NOT NULL UNIQUE,           -- confirm/unsubscribe links, no login needed
  confirmed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  confirmed_at TEXT,
  ip_hash TEXT,                          -- for signup rate-limiting, same pattern as reports.ip_hash
  UNIQUE(exchange_id, email)
);
CREATE INDEX IF NOT EXISTS idx_watchers_token ON watchers(token);
CREATE INDEX IF NOT EXISTS idx_watchers_exchange_confirmed ON watchers(exchange_id, confirmed);
