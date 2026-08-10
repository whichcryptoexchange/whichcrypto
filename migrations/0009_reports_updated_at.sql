-- Tracks when a moderator edits a report (before or after publishing) --
-- reports were previously only ever approved/rejected exactly as
-- submitted; this supports actually editing the fields (e.g. redacting
-- something in `detail` before it goes public, or correcting a mistake
-- in an already-approved one).
ALTER TABLE reports ADD COLUMN updated_at TEXT;
