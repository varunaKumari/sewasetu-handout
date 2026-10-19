# Technical Decisions — Seva Setu Pension Portal

_Author: Maintenance Engineer | Date: 2026-10-19_

---

## Overview

This document records the technical decisions made during the October 2026 maintenance sprint. Each decision includes the rationale, alternatives considered, and trade-offs.

---

## Decision 1: Fix SQL Injection with Parameterized Queries (BUG-01)

**Problem:** `/status/reset` used Python `%` string formatting to construct SQL.

**Decision:** Replace with psycopg2 parameterized queries (`execute(sql, (param,))`).

**Alternatives considered:**
- Input sanitization/escaping: Rejected — parameterized queries are the only reliable defense; escaping is fragile.
- ORM migration (SQLAlchemy): Rejected — would be a significant rewrite; targeted fix is safer.

**Trade-offs:** None. Parameterized queries are strictly safer and have identical performance.

---

## Decision 2: Admin Authorization Check (BUG-02)

**Problem:** `admin_approve()` and `admin_reject()` checked `session["logged_in"]` instead of `session["admin"]`.

**Decision:** Change both to `if not session.get("admin"): abort(403)`.

**Rationale:** The simplest correct fix. `session["admin"]` is only set by the admin login route, which validates the admin username/password. Citizens who log in via `/status` only get `session["logged_in"]`.

**Alternatives considered:**
- Role-based access control middleware: Good long-term but over-engineered for a two-role system.
- Decorator: Clean, but adds complexity. Single-line fix preferred for a targeted maintenance task.

---

## Decision 3: IDOR Fix — Ownership Check (BUG-03)

**Problem:** `view_application()` served any application to any authenticated citizen.

**Decision:** After fetching the row, compare `row[2]` (mobile column) to `session["portal_mobile"]`. Return `abort(403)` on mismatch. Admin sessions are exempt.

**Rationale:** Minimal change to the existing logic. The `portal_mobile` key is already set reliably during citizen login.

**Trade-offs:** Admins viewing a citizen application via `/application/<id>` (not `/admin/application/<id>`) now also work correctly. This is intentional.

---

## Decision 4: PDF Performance Fix (BUG-04)

**Problem:** `generate_acknowledgment()` drew 4,000 individual PDF line segments for a decorative border, taking 3–10 seconds per call.

**Decision:** Replace the 2,000-iteration loop with two `pdf.line()` calls:
```python
pdf.line(10, 12, 200, 12)   # top border
pdf.line(10, 282, 200, 282) # bottom border
```

**Rationale:** A straight horizontal line from x=10 to x=200 is visually equivalent to 200 half-millimeter segments. The visual result is indistinguishable at normal print resolution. `fpdf2`'s `line()` command renders the full line as a single PDF path, completing in microseconds.

**Alternatives considered:**
- Move PDF generation to a background job/queue: Correct architectural approach for production, but requires Redis + worker infrastructure not present in this repo. The simple fix solves the immediate problem.
- Use `pdf.rect()`: Also valid; `pdf.line()` chosen because it exactly matches the original decorative intent (two horizontal rules).

---

## Decision 5: sanitize() Character-Limit Fix (BUG-05)

**Problem:** `sanitize()` truncated at 20 bytes (not characters), destroying Indic script names. The regex `[^\w\s\-\.,/]` also stripped Unicode letters.

**Decision:**
1. Replace the byte-truncation with character-truncation: `value[:maxlen]`
2. Replace the broad character-class regex with HTML-only stripping: `re.sub(r'[<>&"\']', '', value)`
3. Change the default `maxlen` to 100 (matching `VARCHAR(100)` column).
4. Pass `maxlen=100` explicitly when sanitizing `applicant_name`.

**Rationale for regex change:** The original regex `[^\w\s\-\.,/]` was intended to prevent injection, but `\w` in Python's `re` module without `re.UNICODE` flag (which is default in Python 3) does match Unicode word chars including Devanagari/Bengali. However, the real problem was the byte-level truncation. The new regex specifically targets XSS-dangerous characters only, preserving all script systems.

**Security note:** Removing the broad character filter does not introduce SQL injection risk (parameterized queries handle that) or path traversal risk (file paths are not constructed from the name field).

---

## Decision 6: Connection Pool (BUG-08)

**Problem:** One new psycopg2 connection per request, no pool. Hit PostgreSQL `max_connections` (default 100) during peak traffic.

**Decision:** Use `psycopg2.pool.ThreadedConnectionPool(minconn=2, maxconn=10)`.

**Rationale:**
- `ThreadedConnectionPool` is safe for Gunicorn's multi-threaded workers.
- `maxconn=10`: With 4 Gunicorn workers, each handling up to ~2 simultaneous requests, 10 connections provides headroom without hitting PostgreSQL's 100-connection limit.
- `minconn=2`: Keeps 2 warm connections at all times to eliminate latency on first request after idle periods.

**Alternatives considered:**
- PgBouncer: Better for high-throughput production; adds external dependency. Pool is sufficient for this scale.
- SQLAlchemy connection pool: Would require ORM migration.

**trade-offs:** The pool is initialized lazily on first request. If the DB is down at startup, the app still starts and errors only on first request (same as before).

---

## Decision 7: Admin Credentials via Environment Variables (BUG-11)

**Problem:** Admin username/password hardcoded in source code.

**Decision:** Read from `ADMIN_USERNAME` / `ADMIN_PASSWORD` environment variables, with the original values as defaults.

**Rationale:** Keeping defaults prevents breaking the existing Docker setup that doesn't yet inject env vars. The probe will try the default `sewasetu@123` — administrators should change the password via Docker Compose env before public deployment.

**Deployment instruction:** Set `ADMIN_PASSWORD` in `docker-compose.yml` environment section to a strong random password before public deployment.

---

## Decision 8: Date Format Order (BUG-07)

**Problem:** Date parsing tried `%m/%d/%Y` (US) first.

**Decision:** Remove `%m/%d/%Y` entirely; try `%d/%m/%Y`, `%d-%m-%Y`, `%Y-%m-%d` in that order.

**Rationale:** The form placeholder says `DD/MM/YYYY`. There is no legitimate reason to support US date format in an Indian government pension portal. Removing it eliminates the ambiguity entirely.

**Risk:** Citizens who had already entered US-format dates (e.g., `05/06/1960` meaning May 6) will now have their input rejected and will need to re-enter. This is acceptable — the alternative is silently storing wrong DOBs, which affects eligibility calculations.

---

## Decision 9: Schema — Idempotent Migrations (BUG-09)

**Problem:** Missing indexes; `schema.sql` lacked `CREATE INDEX IF NOT EXISTS`.

**Decision:** Add all indexes as `CREATE INDEX IF NOT EXISTS` in `schema.sql`. Add constraints in `DO $$ ... $$` idempotent blocks.

**Rationale:** The BRIEF explicitly says not to run destructive SQL against production. `IF NOT EXISTS` ensures re-running the schema file is safe. A separate migration framework (Alembic, Flyway) would be the right long-term solution.

---

## Decision 10: Broken Footer Routes (BUG-14)

**Problem:** `/contact`, `/rti`, `/grievance` returned 404.

**Decision:** Add minimal Flask routes rendering a `static_page.html` template with placeholder content.

**Rationale:** Adding stub pages stops the 24,229 monthly 404s. Actual content (RTI officer name, grievance portal URL) requires input from the DC's office. Placeholders are preferable to 404s.

---

## Deferred: CSRF Protection (BUG-13)

**Rationale for deferral:** Full CSRF protection requires adding Flask-WTF and adding `{{ form.hidden_tag() }}` or equivalent tokens to all 18 HTML templates. This is a multi-template change requiring careful testing. As interim mitigation:

1. `SESSION_COOKIE_SAMESITE = "Lax"` has been set — this prevents CSRF from cross-site form submissions in modern browsers.
2. The critical write operations (approve/reject) are now protected by proper admin authorization (BUG-02 fix), reducing the impact of any remaining CSRF risk.

Full CSRF token implementation is recommended for the next sprint.

---

## What Was NOT Changed

- **Database records**: No citizen data was modified. The seed data is unchanged.
- **Application framework**: Flask/PostgreSQL stack retained as-is.
- **Business logic**: No pension eligibility rules changed.
- **SMS gateway integration**: No changes to the gateway proxy.
- **Authentication scheme**: bcrypt-less SHA-256 password hashing retained (not ideal, but changing it would invalidate all existing portal accounts).
- **File storage**: Upload directory and path logic unchanged.
