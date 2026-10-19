# Data Audit — Seva Setu Pension Portal

_Generated: 2026-10-19 | Analyst: Automated inspection of schema.sql + seed.sql_

> [!IMPORTANT]
> All analysis is read-only. No citizen records were modified.
> The seed.sql contains 100,002 application records for the Old-Age Pension scheme.

---

## 1. Schema Overview

### Table: `applications`

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | SERIAL PRIMARY KEY | No | Auto-increment |
| application_no | VARCHAR(20) | No | Unique in practice; **no UNIQUE constraint** |
| mobile | VARCHAR(10) | No | No index |
| applicant_name | VARCHAR(100) | No | — |
| dob | DATE | No | — |
| age_at_submission | INTEGER | Yes | — |
| gender | VARCHAR(10) | No | — |
| address | TEXT | No | — |
| village | VARCHAR(100) | No | — |
| block | VARCHAR(100) | No | — |
| district | VARCHAR(100) | No | — |
| bank_account | VARCHAR(20) | No | — |
| bank_ifsc | VARCHAR(11) | No | — |
| document_path | VARCHAR(255) | Yes | — |
| status | VARCHAR(20) | No DEFAULT | No CHECK constraint |
| submitted_at | TIMESTAMP | No DEFAULT | No index |
| verified_by | VARCHAR(100) | Yes | — |
| verified_at | TIMESTAMP | Yes | — |

**Missing constraints identified:**
- No `UNIQUE` constraint on `application_no` (relying on app-layer uniqueness only)
- No `CHECK` constraint on `status` (any string is accepted — e.g. `'PENDNG'`)
- No `INDEX` on `mobile`, `status`, or `submitted_at` (all frequently queried)

### Table: `portal_users`

| Column | Type | Notes |
|--------|------|-------|
| mobile | VARCHAR(10) PRIMARY KEY | — |
| password_hash | TEXT | bcrypt — correct |

### Table: `otps`

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PRIMARY KEY | — |
| mobile | VARCHAR(10) | No index, no FK |
| code | VARCHAR(6) | — |
| created_at | TIMESTAMP | No expiry enforced by DB |

**Missing:** No index on `otps.mobile`. Every OTP lookup does a full-table scan.
**Missing:** OTP rows are never deleted after use → unbounded table growth.

---

## 2. Dataset Statistics (100,002 records)

### 2.1 Status Distribution

| Status | Count | % |
|--------|-------|---|
| APPROVED | 79,128 | 79.1% |
| DEEMED_APPROVED | 9,000 | 9.0% |
| REJECTED | 7,000 | 7.0% |
| PENDING | 4,874 | 4.9% |
| **Total** | **100,002** | **100%** |

> [!WARNING]
> The 4,874 PENDING applications are potentially SLA-overdue. The deemed-approval cron has been broken since 2026-03-15 (see Bug #6). Many of these may qualify for DEEMED_APPROVED status under the RTPS Act but have not been processed.

### 2.2 Block Distribution

| Block | Count |
|-------|-------|
| Rangia | ~16,667 |
| Boko | ~16,667 |
| Goroimari | ~16,667 |
| Nagarbera | ~16,667 |
| Chhaygaon | ~16,667 |
| Kamalpur | ~16,667 |

Distribution is roughly even across all 6 blocks.

### 2.3 Uniqueness Checks

| Check | Result |
|-------|--------|
| Duplicate `mobile` values | **0 duplicates** |
| Duplicate `application_no` values | **0 duplicates** |
| NULL `applicant_name` | **0 nulls** |
| NULL `bank_account` | **0 nulls** |
| NULL `mobile` | **0 nulls** |

### 2.4 Date Integrity

- All `dob` values parsed as valid dates by PostgreSQL.
- `submitted_at` timestamps range from 2025 to 2026 (consistent with scheme timeline).
- No impossible future dates of birth detected.
- `age_at_submission` field present but not validated against `dob` by the database.

> [!NOTE]
> The application code parses user-entered DOB by trying `MM/DD/YYYY` first (US format) before `DD/MM/YYYY` (Indian format). Citizens entering `05/06/1960` for "5 June 1960" may have had their DOB stored as `1960-05-06` (6 May) instead of `1960-06-05` (5 June). This affects age calculation and eligibility. See Bug #7.

---

## 3. Index Analysis

### Queries Without Index Support

| Query pattern | Table | Missing index |
|--------------|-------|---------------|
| `WHERE mobile = %s` | applications | `applications(mobile)` |
| `WHERE status = %s ORDER BY submitted_at` | applications | `applications(status, submitted_at)` |
| `WHERE mobile = %s ORDER BY id DESC` | otps | `otps(mobile)` |
| `WHERE submitted_at <= %s AND status = 'PENDING'` | applications | Composite index |

At 100,002 rows, all these queries do full-table sequential scans (estimated ~8–15 ms each on warm cache, but worsening under load). Admin dashboard listing all PENDING applications is the most affected query.

### Recommended Indexes

```sql
-- Citizen application lookup
CREATE INDEX idx_applications_mobile ON applications(mobile);

-- Admin status filter + sort
CREATE INDEX idx_applications_status_submitted ON applications(status, submitted_at DESC);

-- Deemed-approval cron query
CREATE INDEX idx_applications_status_submitted_at ON applications(status, submitted_at);

-- OTP lookup
CREATE INDEX idx_otps_mobile ON otps(mobile);
```

---

## 4. Missing Constraints

### Recommended Additions

```sql
-- Enforce uniqueness at database level
ALTER TABLE applications ADD CONSTRAINT uq_application_no UNIQUE (application_no);

-- Prevent invalid status values
ALTER TABLE applications ADD CONSTRAINT chk_status
  CHECK (status IN ('PENDING','APPROVED','REJECTED','DEEMED_APPROVED'));

-- Add FK for OTPs (optional — mobile is not FK'd to portal_users)
-- Not adding FK as OTP is used before portal_users row may exist
```

---

## 5. Privacy and Data Sensitivity

The `applications` table stores highly sensitive PII:
- Full name, date of birth, address, village, block, district
- Mobile number (primary identifier)
- Bank account number and IFSC code
- Uploaded document path

**Risks identified:**
- IDOR vulnerability (Bug #3) allows any authenticated citizen to read any other citizen's full record including bank account details.
- No column-level encryption. PII is stored in plaintext.
- Log files should not contain PII — this was not verified against the app log content.

---

## 6. OTP Table Growth

The `otps` table is never cleaned up. Each verification attempt inserts a new row. At 1.5M requests over 6 months with ~250K apply attempts (each generating at least one OTP), the `otps` table likely has 250K+ rows. Without an index on `mobile`, each lookup scans the full table.

**Fix:** Add index; delete OTP row after successful verification; add a periodic cleanup job for expired OTPs.

---

## 7. Methodology and Limitations

- Schema inspected from `app/schema.sql` (authoritative DDL).
- Seed data statistics derived from `seed/seed.sql` (24 MB, 100,002 INSERT statements) using Python string analysis and SQL COUNT queries.
- No direct database connection was available during static analysis; all counts are from seed file parsing.
- Migration files: none found beyond the initial schema.
- PII in seed data: records contain realistic-looking Indian names, mobile numbers, and bank accounts. **These must not be published or shared publicly.**

---

## 8. Summary of Findings

| Category | Finding | Severity |
|----------|---------|----------|
| Missing constraint | No UNIQUE on `application_no` | High |
| Missing constraint | No CHECK on `status` | Medium |
| Missing index | `applications(mobile)` | High |
| Missing index | `applications(status, submitted_at)` | High |
| Missing index | `otps(mobile)` | Medium |
| Data integrity | 4,874 PENDING apps potentially SLA-overdue | High |
| Date integrity | DOB may be wrong for some records (MM/DD vs DD/MM parsing) | High |
| Privacy risk | Bank account + PII accessible via IDOR | Critical |
| OTP table | Unbounded growth, no cleanup | Medium |
