# Sewa Setu — Old Age Pension Portal

Government of Purvanchal, Department of Social Welfare.

## Quick Start

```bash
docker compose up --build
```

Portal: http://localhost:8000  
SMS Gateway inbox: http://localhost:8000/__gateway/  
Admin panel: http://localhost:8000/admin

**Set environment variables before public deployment** (see `docs/deployment.md`):
```yaml
# In docker-compose.yml, under app → environment:
SECRET_KEY: "<random 32-byte hex>"
ADMIN_USERNAME: "<new username>"
ADMIN_PASSWORD: "<strong password>"
```

## Running Tests

```bash
pip install pytest flask fpdf2 requests psycopg2-binary
pytest tests/test_fixes.py -v
```

All 26 tests pass. No database required for tests.

## Documentation

| Document | Description |
|----------|-------------|
| [docs/initial-assessment.md](docs/initial-assessment.md) | System overview, architecture, investigation plan |
| [docs/log-analysis.md](docs/log-analysis.md) | Six-month log analysis findings |
| [docs/data-audit.md](docs/data-audit.md) | Database schema audit, data quality findings |
| [docs/bug-triage.md](docs/bug-triage.md) | Prioritized bug list with evidence and status |
| [docs/technical-decisions.md](docs/technical-decisions.md) | Engineering decisions and rationale |
| [docs/testing.md](docs/testing.md) | Test architecture and coverage |
| [docs/deployment.md](docs/deployment.md) | Deployment instructions |
| [docs/known-limitations.md](docs/known-limitations.md) | Deferred issues and known gaps |
| [analysis/log_analysis.py](analysis/log_analysis.py) | Reproducible log analysis script |

## Fixes Applied (2026-10-19)

Ranked by citizen impact:

| # | Bug | Description | Users Affected |
|---|-----|-------------|----------------|
| 1 | BUG-01 | **SQL injection** in `/status/reset` → parameterized queries | All 100,002 citizens |
| 2 | BUG-02 | **Admin auth bypass** → citizens could approve/reject pensions | All applications |
| 3 | BUG-03 | **IDOR** → any citizen could view others' bank accounts + PII | All 100,002 citizens |
| 4 | BUG-04 | **13,759 failed submissions** (PDF loop) → replace with 2 line calls | 13,759 citizens |
| 5 | BUG-05 | **Indian names truncated** at 20 bytes → character-limit fix | All Indic-script users |
| 6 | BUG-06 | **Deemed-approval cron broken** 220+ days → fix config filename | All PENDING apps |
| 7 | BUG-07 | **Wrong date format** (US before India) → swap to DD/MM/YYYY first | Ambiguous DOB citizens |
| 8 | BUG-08 | **DB connection exhaustion** → ThreadedConnectionPool | Peak traffic users |
| 9 | BUG-09 | **Missing DB indexes** → added on mobile, status, submitted_at | All citizens (perf) |
| 10 | BUG-10 | OTP not deleted after use → delete on success | All users |
| 11 | BUG-11 | Hardcoded admin credentials → env vars | Admin accounts |
| 12 | BUG-12 | Hardcoded secret key → env var | All sessions |
| 14 | BUG-14 | Footer links 404 → stub routes for /contact /rti /grievance | All visitors |
| 15 | BUG-15 | Upload UI says "JPG/5MB" → corrected to "PDF/100KB" | All applicants |

## Admin Credentials

Default (MUST CHANGE before production):
- Username: `admin`  
- Password: `sewasetu@123`

Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables to override.
