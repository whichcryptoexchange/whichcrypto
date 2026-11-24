-- Per-jurisdiction licence alerts, layered onto the existing weekly digest
-- list rather than a separate table: the content is the same register diff,
-- just filtered. Comma-separated country codes (e.g. 'SK,CZ'); NULL means
-- the full roundup, which is what every pre-existing subscriber keeps.
ALTER TABLE digest_subscribers ADD COLUMN countries TEXT;
