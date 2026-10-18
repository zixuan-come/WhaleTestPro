-- Keep legacy tag/suite targets unchanged. Run once on main and shadow DBs.
ALTER TABLE schedule ADD COLUMN selection JSON NULL;
ALTER TABLE schedule ADD COLUMN notify BOOLEAN NOT NULL DEFAULT 0;
