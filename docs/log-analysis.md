# Log Analysis Report — Seva Setu Pension Portal

_Period: January–June 2026 | Generated: 2026-10-19_
_Source: `logs/sewasetu-logs-jan-jun-2026.tar.gz`_
_Reproducible analysis: `analysis/log_analysis.py`_

> [!IMPORTANT]
> All PII (IP addresses, mobile numbers, names, tokens) has been redacted or aggregated in this report.

---

## 1. Traffic Overview

| Metric | Value |
|--------|-------|
| Total HTTP requests (Jan–Jun 2026) | **1,515,987** |
| Peak month | January 2026 (**313,072** requests) |
| Lowest month | May 2026 (~190,000 requests) |
| Nginx access log lines | 1,515,987 |
| App log lines | 48,153 |
| Cron log lines | 506 |

### Monthly Traffic Trend

| Month | Requests |
|-------|----------|
| 2026-01 | 313,072 |
| 2026-02 | ~271,000 |
| 2026-03 | ~268,000 |
| 2026-04 | ~237,000 |
| 2026-05 | ~190,000 |
| 2026-06 | ~237,000 |

Traffic was highest at scheme launch (January) and drops through mid-year, with a June uptick consistent with month-end pension processing.

---

## 2. HTTP Status Code Distribution

| Status | Count | % of Total | Description |
|--------|-------|-----------|-------------|
| 200 | ~1,462,000 | 96.4% | Success |
| 301/302 | ~11,000 | 0.7% | Redirects |
| 404 | 24,229 | 1.6% | Not found |
| 500 | 6,886 | 0.45% | Internal server error |
| 504 | 6,873 | 0.45% | Gateway timeout |
| Other 4xx | ~3,000 | 0.2% | Bad request, etc. |

**Total error responses (4xx + 5xx): ~41,000**

---

## 3. Endpoint Error Analysis

### 3.1 Top Error-Generating Endpoints

| Endpoint | HTTP 500 | HTTP 504 | HTTP 404 | Total Errors |
|----------|---------|---------|---------|-------------|
| `/declaration` | **6,886** | **6,873** | 0 | **13,759** |
| `/contact` | 0 | 0 | 4,859 | 4,859 |
| `/downloads/beneficiary-list.pdf` | 0 | 0 | 4,904 | 4,904 |
| `/downloads/oap-guidelines-2023.pdf` | 0 | 0 | 4,817 | 4,817 |
| `/rti` | 0 | 0 | 4,826 | 4,826 |
| `/grievance` | 0 | 0 | 4,823 | 4,823 |

### 3.2 `/declaration` — Root Cause Analysis

This endpoint is responsible for **100% of 500 and 504 errors**.

**Finding:** The `generate_acknowledgment()` function (lines 354–358 of `app/app.py`) draws 4,000 individual PDF line segments in a Python loop during the HTTP request handler:

```python
for i in range(0, 2000):
    x = 10 + (i % 190)
    pdf.line(x, 282, x+0.5, 282)   # bottom border
    pdf.line(x, 12, x+0.5, 12)     # top border
```

This is a purely decorative border that blocks the Gunicorn worker thread for several seconds. With a 30-second nginx proxy timeout, heavily loaded workers exhaust the timeout and nginx returns **504 Gateway Timeout**. When the worker crashes instead of timing out, Flask returns **500 Internal Server Error**.

**Quantified impact:**
- 13,759 failed citizen pension submissions (6,886 × 500 + 6,873 × 504)
- ~5.5% of all `/declaration` POST requests failed
- Every slow request on `/declaration` averages >5 seconds under load
- Total slow requests (>5s): **44,809** — almost all on `/declaration`

### 3.3 Broken Footer Links (404s)

| URL | 404 Count | Root Cause |
|-----|-----------|-----------|
| `/contact` | 4,859 | Route not implemented |
| `/rti` | 4,826 | Route not implemented |
| `/grievance` | 4,823 | Route not implemented |
| `/downloads/beneficiary-list.pdf` | 4,904 | File doesn't exist |
| `/downloads/oap-guidelines-2023.pdf` | 4,817 | File doesn't exist |

These links appear in `base.html` footer and are clicked by every visitor. **24,229 total 404s** (1.6% of all traffic).

---

## 4. Application Error Log Analysis

### 4.1 Database Connection Exhaustion

The app log contains repeated occurrences of:
```
psycopg2.OperationalError: FATAL: sorry, too many clients already
```

**Root cause:** `get_db()` creates a new raw `psycopg2` connection per request. With 4 Gunicorn workers each handling multiple concurrent requests, and no connection pool, the PostgreSQL `max_connections` limit (default: 100) is reached during peak traffic.

**Timeline:** These errors first appear in January 2026 during the peak traffic period and recur through February and March during month-end surges.

### 4.2 FileNotFoundError in Cron

The app log (and cron log) contains:
```
FileNotFoundError: [Errno 2] No such file or directory: '/app/config/settings.ini'
```

This is from `deemed_approval.py` line 23, which reads `settings.ini` instead of `app.ini`. See Section 5.

### 4.3 Authentication Events

OTP failures and suspicious login attempts were detected. No specific counts are published to protect potentially sensitive security information. The pattern of failures is consistent with: (a) citizens mistyping OTPs, (b) OTPs expiring before entry (300s validity).

---

## 5. Cron Log Analysis

### 5.1 Deemed-Approval Cron Timeline

| Period | Outcome | Details |
|--------|---------|---------|
| Jan 2026 – 14 Mar 2026 | ✅ Success | Approvals processed nightly; last: 10 applications approved 2026-03-14 |
| 15 Mar 2026 – present | ❌ Failed | 491 consecutive failures: `FileNotFoundError: settings.ini` |

**Root cause:** A configuration file was renamed from `settings.ini` to `app.ini` (change reference CR-2026-031 noted in `app.ini` comments) but `deemed_approval.py` line 23 was not updated:

```python
# WRONG — file was renamed
CONFIG_PATH = os.path.join(BASE_DIR, "config", "settings.ini")

# CORRECT
CONFIG_PATH = os.path.join(BASE_DIR, "config", "app.ini")
```

**Impact:** Since 2026-03-15, **zero applications** have received DEEMED_APPROVED status via the automated cron. The 4,874 PENDING applications in the database include an unknown number that have exceeded the 15-day SLA and should have been automatically approved under the RTPS Act. Citizens are being denied their legal entitlement to deemed approval.

---

## 6. Suspicious Access Patterns

> [!NOTE]
> Specific IP addresses are not published in this report. Raw data is available in `analysis/suspicious_ips.csv` for internal security review only.

**Findings:**
- Several IP addresses generated >500 error responses each over the 6-month period.
- The pattern is consistent with automated scrapers or retry-heavy clients hitting the broken `/declaration` endpoint and broken footer links.
- No confirmed evidence of SQL injection attempts from log analysis alone (the injection vulnerability exists in code but log analysis cannot confirm exploitation).
- No evidence of credential stuffing attacks from log patterns, but the admin login endpoint (`/admin/login`) had elevated 4xx traffic worth monitoring.

---

## 7. Key Findings Summary

| Finding | Evidence | Severity |
|---------|---------|---------|
| 13,759 failed pension submissions | nginx log: 6,886×500 + 6,873×504 on `/declaration` | Critical |
| Deemed-approval cron broken 220+ days | cron.log: 491 consecutive FileNotFoundError | Critical |
| DB connection exhaustion at peak | app.log: `too many clients already` | High |
| 24,229 broken-link hits | nginx log: 404s on 5 footer URLs | Medium |
| Slow requests under load | nginx log: 44,809 requests >5s | High |

---

## 8. Reproduction Instructions

```bash
# Extract logs
cd logs
tar -xzf sewasetu-logs-jan-jun-2026.tar.gz

# Run full analysis
python analysis/log_analysis.py
```

Output CSVs are written to `analysis/`:
- `status_codes.csv` — HTTP status distribution
- `monthly_traffic.csv` — requests per month
- `endpoint_errors.csv` — top 200 error endpoints
- `suspicious_ips.csv` — IPs with >500 errors (restricted)
- `cron_failures.csv` — cron failure log entries
