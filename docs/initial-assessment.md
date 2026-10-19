# Initial Assessment — Seva Setu Pension Portal

_Generated: 2026-10-19_

## 1. System Overview

**Seva Setu** is a state-government citizen-facing pension portal for the Old-Age Pension (OAP) scheme. Citizens submit applications online; officials verify and approve them; approved citizens receive pension payments and SMS notifications.

| Item | Value |
|------|-------|
| Framework | Flask 2.2.5 (Python 3.11) |
| Database | PostgreSQL 15 |
| WSGI server | Gunicorn (4 workers, 30s timeout) |
| Containerisation | Docker Compose (services: `db`, `app`, `scheduler`, `smsgw`) |
| PDF generation | fpdf2 2.7.4 |
| SMS | Fake gateway at `http://smsgw:8025` (internal network) |
| Configuration | `app/config/app.ini` (INI file) |
| Auth | Session cookies (Flask `secret_key`); admin = hardcoded username/password |
| Deployment target | Single-port public deployment; SMS proxy at `/__gateway/` |

## 2. Repository Structure

```
sewasetu-handout/
├── BRIEF.md                    ← Primary requirements
├── README.md                   ← Setup: `docker compose up --build`
├── dc-briefing.mp3             ← Deputy Commissioner audio briefing
├── docker-compose.yml          ← 4 services: db, app, scheduler, smsgw
├── app/
│   ├── app.py                  ← Single-file Flask application (586 lines)
│   ├── schema.sql              ← PostgreSQL schema (3 tables)
│   ├── requirements.txt        ← Python dependencies
│   ├── Dockerfile              ← python:3.11-slim, cron, gunicorn
│   ├── config/app.ini          ← DB creds, secret key, SMS URL, scheme config
│   ├── scripts/
│   │   └── deemed_approval.py  ← Nightly cron: auto-approve SLA-overdue apps
│   ├── deploy/crontab          ← Schedules deemed_approval.py at 02:00 daily
│   └── templates/              ← 18 Jinja2 HTML templates
├── smsgw/app.py                ← Fake SMS gateway (Flask, logs messages)
├── logs/
│   └── sewasetu-logs-jan-jun-2026.tar.gz  ← 6-month server logs
└── seed/seed.sql               ← 100,002 citizen application records
```

## 3. Application Architecture

### User Journeys
1. **Apply** → `/apply` → OTP sent → `/verify` → `/form/1-3` → `/upload` → `/declaration` → confirmation
2. **Status check** → `/status` login → `/application/<id>` (citizen's own record)
3. **Password reset** → `/status/reset`
4. **Admin** → `/admin/login` → `/admin/dashboard` → approve/reject applications

### Database Tables
- **`applications`** — one row per pension application (18 columns, no indexes)
- **`portal_users`** — citizen portal login (mobile PK, bcrypt password hash)
- **`otps`** — one-time passwords for mobile verification

## 4. Dataset

- **100,002 application records** loaded via `seed/seed.sql`
- Status distribution: APPROVED 79,128 (79.1%), DEEMED_APPROVED 9,000 (9.0%), REJECTED 7,000 (7.0%), PENDING 4,874 (4.9%)
- 6 blocks, ~16,500 applications each
- No duplicate mobiles or application numbers
- No null names or bank accounts found

## 5. Six-Month Log Summary

Logs cover January–June 2026 (extracted from `logs/sewasetu-logs-jan-jun-2026.tar.gz`):

| Log file | Lines | Coverage |
|----------|-------|----------|
| `nginx-access.log` | 1,515,987 | All HTTP requests |
| `sewasetu-app.log` | 48,153 | Flask/Gunicorn events |
| `cron.log` | 506 | Nightly deemed-approval runs |

Total requests: **1,515,987** over 6 months.

Peak month: January 2026 (313,072 requests).

## 6. Critical Problems Identified

| # | Severity | Description |
|---|----------|-------------|
| 1 | CRITICAL | SQL injection in `/status/reset` (password reset) |
| 2 | CRITICAL | Admin auth bypass — any citizen can approve/reject applications |
| 3 | CRITICAL | IDOR — any citizen can view any other citizen's application |
| 4 | CRITICAL | 13,759 failed submissions due to slow PDF generation (504/500 on `/declaration`) |
| 5 | CRITICAL | Indian-language names silently truncated (byte-level truncation) |
| 6 | HIGH | Deemed-approval cron broken since 2026-03-15 (wrong config filename) |
| 7 | HIGH | Date parsing tries MM/DD/YYYY first (wrong for India — should be DD/MM/YYYY) |
| 8 | HIGH | DB connection leak — "too many clients" errors at peak traffic |
| 9 | MEDIUM | Missing indexes on `applications.mobile`, `status`, `submitted_at`; `otps.mobile` |
| 10 | MEDIUM | OTP not invalidated after use |
| 11 | MEDIUM | Hardcoded admin credentials in source code |
| 12 | MEDIUM | Missing CSRF protection on all POST forms |
| 13 | LOW | Four broken footer links (404: /contact, /rti, /grievance, PDF downloads) |
| 14 | LOW | Upload UI says "JPG or PDF, max 5 MB" but code enforces PDF-only 100 KB |
| 15 | LOW | Step numbering wrong in multi-step form |

## 7. Investigation Plan

1. **Phase 2**: Start Docker, confirm app loads at `http://localhost:8000`.
2. **Phase 3**: Produce `analysis/log_analysis.py` for reproducible log analysis.
3. **Phase 4**: Produce `docs/data-audit.md` from schema + seed SQL inspection.
4. **Phase 5**: Trace each user journey through code and templates.
5. **Phase 6**: Produce `docs/bug-triage.md` with prioritized findings.
6. **Phase 7**: Fix top issues in order (SQL injection → auth bypass → IDOR → PDF perf → Indian names → cron → date parsing → indexes).
7. **Phase 8**: Write tests (fail-before, pass-after), commit in order.
8. **Phase 9**: Deploy publicly (Railway / Render / fly.io).
9. **Phase 10**: `docs/technical-decisions.md`.
10. **Phase 11**: Final acceptance check against probe criteria.

## 8. dc-briefing.mp3

The file exists at the repository root (3 MB MP3). No audio transcription tool is available in this environment. The briefing file has not been transcribed. The BRIEF.md and README.md are treated as the authoritative requirements sources.

## 9. Key Configuration Values

| Setting | Value |
|---------|-------|
| DB host | `db` (Docker service) |
| DB name | `sewasetu` |
| DB user | `sewasetu` |
| Scheme deadline | 2026-10-31 23:59 |
| Min age | 60 years |
| SLA days | 15 |
| OTP validity | 300 seconds |
| Upload dir | `/var/sewasetu/uploads` |
| Admin username | `admin` (hardcoded — **must change**) |
| Admin password | `sewasetu@123` (hardcoded — **must change**) |
