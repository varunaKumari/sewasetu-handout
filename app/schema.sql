-- Sewa Setu Old Age Pension Portal - schema
-- NOTE: seed.sql (shipped separately) loads after this and contains the
-- production data. Do not re-run against a live database.

CREATE TABLE IF NOT EXISTS applications (
    id              SERIAL PRIMARY KEY,
    application_no  VARCHAR(20),
    applicant_name  VARCHAR(100),
    mobile          VARCHAR(15),
    dob             DATE,
    gender          VARCHAR(10),
    marital_status  VARCHAR(20),
    husband_name    VARCHAR(100),
    husband_employer VARCHAR(100),
    village         VARCHAR(100),
    block           VARCHAR(50),
    bank_account    VARCHAR(30),
    ifsc            VARCHAR(15),
    doc_path        VARCHAR(200),
    status          VARCHAR(20) DEFAULT 'PENDING',
    submitted_at    TIMESTAMP,
    decided_at      TIMESTAMP,
    decided_by      VARCHAR(50)
);

-- Status portal accounts (created at submission time)
CREATE TABLE IF NOT EXISTS portal_users (
    mobile        VARCHAR(15) PRIMARY KEY,
    password_hash VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS otps (
    id         SERIAL PRIMARY KEY,
    mobile     VARCHAR(15),
    code       VARCHAR(6),
    created_at TIMESTAMP
);

-- BUG-09 FIX: Add missing indexes identified in data audit.
-- These indexes are IDEMPOTENT (CREATE INDEX IF NOT EXISTS) so they can be
-- safely run on a live database without disrupting existing data.
--
-- Without these, the following queries do full-table sequential scans at
-- 100,000 rows:
--   - Citizen status lookup: WHERE mobile = %s
--   - Admin list by status: WHERE status = %s ORDER BY submitted_at
--   - Deemed-approval cron: WHERE status='PENDING' AND submitted_at < cutoff
--   - OTP verification: WHERE mobile = %s ORDER BY id DESC LIMIT 1

CREATE INDEX IF NOT EXISTS idx_applications_mobile
    ON applications(mobile);

CREATE INDEX IF NOT EXISTS idx_applications_status_submitted
    ON applications(status, submitted_at DESC);

CREATE INDEX IF NOT EXISTS idx_applications_status_submitted_asc
    ON applications(status, submitted_at ASC);

CREATE INDEX IF NOT EXISTS idx_otps_mobile
    ON otps(mobile);

-- BUG-09 FIX: Add missing constraints for data integrity.
-- These use DO $$ ... $$ blocks to be idempotent on re-run.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_application_no'
    ) THEN
        ALTER TABLE applications
            ADD CONSTRAINT uq_application_no UNIQUE (application_no);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_status'
    ) THEN
        ALTER TABLE applications
            ADD CONSTRAINT chk_status
            CHECK (status IN ('PENDING','APPROVED','REJECTED','DEEMED_APPROVED'));
    END IF;
END $$;
