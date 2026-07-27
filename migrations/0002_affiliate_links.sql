-- Affiliate/outbound links: commercial data, deliberately kept out of the
-- regulator-sourced data/exchanges/*.yaml files and their eu_status/countries
-- fields. Managed live via /admin/links, no rebuild needed to update.
CREATE TABLE IF NOT EXISTS affiliate_links (
  exchange_id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  label TEXT,                          -- optional button text override
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
