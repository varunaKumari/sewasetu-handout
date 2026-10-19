# Testing Guide — Seva Setu Pension Portal

_Generated: 2026-10-19_

## Overview

The test suite in `tests/test_fixes.py` covers all 8 major bug fixes. Each test class documents:
- The original bug behavior (what the test would have caught)
- The expected fixed behavior

## Running Tests

```bash
# Install dependencies (if not inside Docker)
pip install pytest flask fpdf2 requests psycopg2-binary

# Run the full suite
pytest tests/test_fixes.py -v

# Run a specific bug's tests
pytest tests/test_fixes.py::TestBug01SqlInjection -v
pytest tests/test_fixes.py::TestBug03Idor -v
```

## Test Architecture

Tests use Flask's built-in test client and `unittest.mock` to mock the database pool — **no real PostgreSQL instance required**. This makes the tests fast and self-contained.

The mock approach patches `get_db()` at the module level, returning a `MagicMock` connection whose cursor returns controlled test data.

## Test Coverage Map

| Test Class | Bug | What is tested |
|-----------|-----|---------------|
| `TestBug01SqlInjection` | BUG-01 | Parameterized query structure; injection payload handled safely |
| `TestBug02AdminAuthBypass` | BUG-02 | Citizen session → 403 on approve/reject; admin session → 302 |
| `TestBug03Idor` | BUG-03 | Cross-citizen application access → 403; own application → 200 |
| `TestBug04PdfPerformance` | BUG-04 | PDF generates in < 2 seconds; output is valid PDF |
| `TestBug05IndianNames` | BUG-05 | Hindi/Bengali names preserved; byte truncation eliminated |
| `TestBug06CronConfigPath` | BUG-06 | Source file references `app.ini` not `settings.ini` |
| `TestBug07DateParsing` | BUG-07 | `05/06/1960` parsed as June 5 (not May 6) |
| `TestBug14FooterRoutes` | BUG-14 | `/contact`, `/rti`, `/grievance` return 200 |
| `TestBug15UploadUiText` | BUG-15 | Template says "PDF only, 100 KB" |
| `TestBug08ConnectionPool` | BUG-08 | Source uses `ThreadedConnectionPool` |
| `TestSecurityHeaders` | BUG-12 | `SESSION_COOKIE_SAMESITE=Lax`, `HTTPONLY=True` |

## Sample Test Output (Expected)

```
tests/test_fixes.py::TestBug01SqlInjection::test_reset_uses_parameterized_query PASSED
tests/test_fixes.py::TestBug01SqlInjection::test_sql_injection_attempt_does_not_return_data PASSED
tests/test_fixes.py::TestBug02AdminAuthBypass::test_citizen_session_cannot_approve PASSED
tests/test_fixes.py::TestBug02AdminAuthBypass::test_citizen_session_cannot_reject PASSED
tests/test_fixes.py::TestBug02AdminAuthBypass::test_unauthenticated_cannot_approve PASSED
tests/test_fixes.py::TestBug02AdminAuthBypass::test_admin_session_can_approve PASSED
tests/test_fixes.py::TestBug03Idor::test_citizen_cannot_view_other_citizens_application PASSED
tests/test_fixes.py::TestBug03Idor::test_citizen_can_view_own_application PASSED
tests/test_fixes.py::TestBug03Idor::test_admin_can_view_any_application PASSED
tests/test_fixes.py::TestBug04PdfPerformance::test_acknowledgment_generates_fast PASSED
tests/test_fixes.py::TestBug04PdfPerformance::test_acknowledgment_contains_no_loop_artifact PASSED
tests/test_fixes.py::TestBug05IndianNames::test_devanagari_name_preserved PASSED
tests/test_fixes.py::TestBug05IndianNames::test_bengali_name_preserved PASSED
tests/test_fixes.py::TestBug05IndianNames::test_long_name_truncated_by_character_not_byte PASSED
tests/test_fixes.py::TestBug05IndianNames::test_html_dangerous_chars_stripped PASSED
tests/test_fixes.py::TestBug05IndianNames::test_english_name_preserved PASSED
...
```

## What Is NOT Covered

- **End-to-end citizen journey**: Requires a running PostgreSQL instance. Test manually with `docker compose up`.
- **SMS gateway integration**: The smsgw is mocked. Test manually via `/__gateway/`.
- **PDF rendering correctness**: Only checks file size and `%PDF` header. Visual inspection needed.
- **Load testing**: The BRIEF mentions a month-end spike probe. Manual load test with `locust` or `ab` is recommended.
- **Deemed-approval cron**: Cannot be unit-tested without DB. Verify by running `docker exec scheduler python /app/scripts/deemed_approval.py` after Docker is up.

## Manual Testing Checklist

After `docker compose up --build`:

- [ ] `curl http://localhost:8000/` — returns 200
- [ ] Apply with a Devanagari name — name appears correctly in confirmation
- [ ] Apply with DOB `05/06/1960` — stored as 1960-06-05 in DB
- [ ] Submit application — confirmation page appears in < 5 seconds
- [ ] `/contact`, `/rti`, `/grievance` — all return 200
- [ ] Log in as citizen, try `/application/1` (another's ID) — returns 403
- [ ] Log in as citizen, POST to `/admin/approve/1` — returns 403
- [ ] Log in as admin (`admin` / check env var), view dashboard — works
- [ ] Admin approves application — status updated in DB
- [ ] `POST /status/reset` with mobile `' OR '1'='1` — returns 200 "If the mobile..." (no crash)
- [ ] Upload JPG file → rejected with error message
- [ ] Upload PDF > 100KB → rejected with error message
- [ ] `/__gateway/` — shows SMS gateway inbox
