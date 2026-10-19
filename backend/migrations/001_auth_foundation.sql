-- Auth foundation migration. Review and run manually; application startup does
-- not execute migrations. Existing trips and itinerary rows are untouched.

BEGIN;

CREATE TABLE IF NOT EXISTS auth_accounts (
    id VARCHAR(36) PRIMARY KEY,
    firebase_uid VARCHAR(128) NOT NULL UNIQUE,
    workspace_id VARCHAR(36) NOT NULL UNIQUE,
    email VARCHAR(320),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMIT;

-- Rollback (run separately, only before account data is needed):
-- BEGIN;
-- DROP TABLE IF EXISTS auth_accounts;
-- COMMIT;
