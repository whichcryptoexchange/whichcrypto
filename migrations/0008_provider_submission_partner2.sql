-- Some providers split custody and execution across two different
-- partners (Nexo's live profile already does: Tangany for custody, DLT
-- Securities for execution), but the submission form only ever captured
-- one. Adds an optional second partner rather than forcing everyone
-- through a single free-text field or a dropdown that can't cover every
-- real custodian name.
ALTER TABLE provider_submissions ADD COLUMN partner2_name TEXT;
ALTER TABLE provider_submissions ADD COLUMN partner2_role TEXT;
