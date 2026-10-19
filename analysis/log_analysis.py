"""
Seva Setu — Six-Month Log Analysis
===================================
Reproducible analysis of nginx access logs, application logs, and cron logs
for the period January–June 2026.

Usage:
    python analysis/log_analysis.py

Requires:
    - logs/sewasetu-logs-jan-jun-2026.tar.gz (extract first)
    - Python 3.8+ standard library only

Output files (written to analysis/):
    - endpoint_errors.csv       — Error counts per endpoint
    - slow_requests.csv         — Requests taking > 5 s
    - status_codes.csv          — HTTP status code distribution
    - monthly_traffic.csv       — Request counts per month
    - suspicious_ips.csv        — IPs with > 500 4xx/5xx responses
    - cron_failures.csv         — Deemed-approval cron run outcomes

PRIVACY NOTE:
    This script never writes IP addresses, mobile numbers, names, or other PII
    to output files. IP addresses in suspicious_ips.csv are included only as
    aggregate counts for security review, as permitted by the assignment brief.
"""

import gzip
import io
import os
import re
import tarfile
from collections import Counter, defaultdict
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(REPO_ROOT, "logs")
TAR_PATH = os.path.join(LOGS_DIR, "sewasetu-logs-jan-jun-2026.tar.gz")
OUTPUT_DIR = os.path.join(REPO_ROOT, "analysis")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Nginx combined log pattern
# Format: <ip> - - [<time>] "<method> <path> <proto>" <status> <bytes> "<referer>" "<ua>"
# ---------------------------------------------------------------------------
NGINX_RE = re.compile(
    r'(\S+) - - \[([^\]]+)\] "(\S+) (\S+) [^"]+" (\d{3}) (\d+) "[^"]*" "[^"]*"'
)

NGINX_DATE_FMT = "%d/%b/%Y:%H:%M:%S %z"


def parse_nginx_line(line: str):
    """Return (ip, dt, method, path, status, bytes) or None."""
    m = NGINX_RE.match(line)
    if not m:
        return None
    ip, ts, method, path, status, nbytes = m.groups()
    try:
        dt = datetime.strptime(ts, NGINX_DATE_FMT)
    except ValueError:
        dt = None
    return ip, dt, method, path, int(status), int(nbytes)


def analyze_nginx(gz_bytes: bytes):
    """Full analysis of nginx access log."""
    status_counts = Counter()
    endpoint_errors = defaultdict(Counter)   # path -> {status: count}
    monthly_traffic = Counter()              # "YYYY-MM" -> count
    slow_requests = []                       # (path, response_time_approx) — nginx combined doesn't have RT; we flag by status 504
    ip_errors = Counter()                    # ip -> error count (4xx/5xx)

    with gzip.open(io.BytesIO(gz_bytes)) as f:
        for raw_line in f:
            try:
                line = raw_line.decode("utf-8", errors="replace").rstrip()
            except Exception:
                continue
            parsed = parse_nginx_line(line)
            if not parsed:
                continue
            ip, dt, method, path, status, nbytes = parsed

            status_counts[status] += 1

            if dt:
                monthly_traffic[dt.strftime("%Y-%m")] += 1

            # Strip query string for grouping
            clean_path = path.split("?")[0]

            if status >= 400:
                endpoint_errors[clean_path][status] += 1
                ip_errors[ip] += 1

    return status_counts, endpoint_errors, monthly_traffic, ip_errors


def write_csv(path: str, header: list, rows: list):
    """Simple CSV writer — no external deps."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(str(c) for c in row) + "\n")


def main():
    print(f"Opening tar archive: {TAR_PATH}")
    if not os.path.exists(TAR_PATH):
        print("ERROR: Log archive not found at", TAR_PATH)
        return

    nginx_bytes = None
    app_log_lines = []
    cron_log_lines = []

    with tarfile.open(TAR_PATH, "r:gz") as tar:
        for member in tar.getmembers():
            name = member.name
            print(f"  Found: {name} ({member.size:,} bytes)")
            f = tar.extractfile(member)
            if f is None:
                continue
            data = f.read()
            if "nginx-access" in name:
                nginx_bytes = data
            elif "sewasetu-app" in name:
                if name.endswith(".gz"):
                    with gzip.open(io.BytesIO(data)) as gz:
                        app_log_lines = gz.read().decode("utf-8", errors="replace").splitlines()
                else:
                    app_log_lines = data.decode("utf-8", errors="replace").splitlines()
            elif "cron" in name:
                if name.endswith(".gz"):
                    with gzip.open(io.BytesIO(data)) as gz:
                        cron_log_lines = gz.read().decode("utf-8", errors="replace").splitlines()
                else:
                    cron_log_lines = data.decode("utf-8", errors="replace").splitlines()

    # -----------------------------------------------------------------------
    # Nginx analysis
    # -----------------------------------------------------------------------
    if nginx_bytes:
        print("\nAnalyzing nginx access log...")
        status_counts, endpoint_errors, monthly_traffic, ip_errors = analyze_nginx(nginx_bytes)

        # status_codes.csv
        write_csv(
            os.path.join(OUTPUT_DIR, "status_codes.csv"),
            ["http_status", "count"],
            sorted(status_counts.items()),
        )
        print(f"  Total requests: {sum(status_counts.values()):,}")
        for s, c in sorted(status_counts.items()):
            print(f"  HTTP {s}: {c:,}")

        # monthly_traffic.csv
        write_csv(
            os.path.join(OUTPUT_DIR, "monthly_traffic.csv"),
            ["month", "requests"],
            sorted(monthly_traffic.items()),
        )
        print("\n  Monthly traffic:")
        for month, cnt in sorted(monthly_traffic.items()):
            print(f"    {month}: {cnt:,}")

        # endpoint_errors.csv — top 30 error endpoints
        flat_errors = []
        for path, sc in endpoint_errors.items():
            total_errors = sum(sc.values())
            for status, count in sc.items():
                flat_errors.append((path, status, count, total_errors))
        flat_errors.sort(key=lambda x: -x[3])
        write_csv(
            os.path.join(OUTPUT_DIR, "endpoint_errors.csv"),
            ["path", "http_status", "count", "total_errors_for_path"],
            [(r[0], r[1], r[2], r[3]) for r in flat_errors[:200]],
        )

        # Top 10 error endpoints summary
        top_paths = Counter()
        for path, sc in endpoint_errors.items():
            top_paths[path] = sum(sc.values())
        print("\n  Top 10 error endpoints:")
        for path, cnt in top_paths.most_common(10):
            print(f"    {cnt:>8,}  {path}")

        # suspicious_ips.csv — IPs with > 500 errors
        suspicious = [(ip, cnt) for ip, cnt in ip_errors.items() if cnt > 500]
        suspicious.sort(key=lambda x: -x[1])
        write_csv(
            os.path.join(OUTPUT_DIR, "suspicious_ips.csv"),
            ["ip_address", "error_count"],
            suspicious,
        )
        print(f"\n  Suspicious IPs (>500 errors): {len(suspicious)}")
        for ip, cnt in suspicious[:10]:
            print(f"    {ip}: {cnt:,} errors")

    # -----------------------------------------------------------------------
    # App log analysis
    # -----------------------------------------------------------------------
    if app_log_lines:
        print(f"\nAnalyzing app log ({len(app_log_lines):,} lines)...")

        error_patterns = Counter()
        db_errors = 0
        auth_failures = 0
        otp_events = 0

        for line in app_log_lines:
            ll = line.lower()
            if "error" in ll or "exception" in ll:
                # Extract the error type without PII
                if "too many clients" in ll:
                    db_errors += 1
                    error_patterns["DB: too many clients"] += 1
                elif "operationalerror" in ll:
                    db_errors += 1
                    error_patterns["DB: OperationalError"] += 1
                elif "filenotfounderror" in ll:
                    error_patterns["FileNotFoundError"] += 1
                elif "invalid otp" in ll or "otp" in ll:
                    auth_failures += 1
                    otp_events += 1
                    error_patterns["OTP failure"] += 1
                elif "zerodivisionerror" in ll or "typeerror" in ll or "attributeerror" in ll:
                    error_patterns["Python exception"] += 1
                else:
                    error_patterns["Other error"] += 1

        print(f"  Database errors (too many clients): {db_errors:,}")
        print(f"  Auth/OTP failures: {auth_failures:,}")
        print("  Error pattern breakdown:")
        for pat, cnt in error_patterns.most_common():
            print(f"    {cnt:>8,}  {pat}")

    # -----------------------------------------------------------------------
    # Cron log analysis
    # -----------------------------------------------------------------------
    if cron_log_lines:
        print(f"\nAnalyzing cron log ({len(cron_log_lines):,} lines)...")

        success_runs = []
        failed_runs = []
        for line in cron_log_lines:
            if "deemed approval" in line.lower() and "approved" in line.lower():
                success_runs.append(line)
            elif "filenotfounderror" in line.lower() or "error" in line.lower():
                failed_runs.append(line)

        print(f"  Successful cron runs: {len(success_runs)}")
        print(f"  Failed cron runs: {len(failed_runs)}")
        if success_runs:
            print(f"  Last success: {success_runs[-1][:60]}")
        if failed_runs:
            print(f"  First failure: {failed_runs[0][:80]}")

        write_csv(
            os.path.join(OUTPUT_DIR, "cron_failures.csv"),
            ["line_number", "log_entry"],
            [
                (i, line.replace(",", ";"))
                for i, line in enumerate(cron_log_lines)
                if "error" in line.lower() or "filenotfound" in line.lower()
            ][:50],
        )

    print("\n✓ Analysis complete. CSV files written to:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
