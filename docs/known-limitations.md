# Known Limitations — Seva Setu Pension Portal

_Generated: 2026-10-19_

## 1. Deferred Security Fixes

### CSRF Protection (BUG-13 — Deferred)
Full CSRF token protection was not implemented in this sprint. Adding Flask-WTF requires template changes across all 18 HTML files and functional testing of each form. As interim mitigation, `SESSION_COOKIE_SAMESITE = "Lax"` has been set, which prevents CSRF from cross-site requests in modern browsers (Chrome, Firefox, Edge). CSRF from same-site navigation is not prevented. This should be addressed in the next sprint.

### Password Hashing (Not BUG-listed)
The portal uses SHA-256 for password hashing (`hashlib.sha256`). SHA-256 is not a password-specific hashing function — it is fast, which makes brute-force attacks cheaper. The existing `portal_users` table uses this scheme and the passwords are already derived from DOBs (weakly predictable). Migrating to bcrypt or argon2 would require a password reset for all ~100K users. This is flagged as a known limitation but was not changed to avoid disrupting the existing user base.

## 2. Data Accuracy Limitations

### DOB Accuracy for Existing Records
The date parsing bug (BUG-07) has been fixed going forward, but records already in the database may have incorrect DOBs if they were submitted with ambiguous dates (e.g., `05/06/1960`) that were misinterpreted as US format. There is no way to retroactively correct these without contacting the affected citizens. Estimated affected records: any citizens whose birth day and month are both ≤ 12 and who submitted before the fix was applied.

### Deemed-Approval Backlog
The deemed-approval cron was broken from 2026-03-15 to 2026-10-19 (~7 months). An unknown number of the 4,874 PENDING applications have exceeded the 15-day SLA and legally qualify for DEEMED_APPROVED status. The fixed cron will process these automatically on its next run (02:00 nightly). No manual intervention should be required. This is a feature, not a limitation — but the backlog may result in a large batch of DEEMED_APPROVED transitions and SMS notifications on the first successful cron run.

## 3. Performance Limitations

### File Uploads in Docker Volume
Uploaded documents and acknowledgment PDFs are stored in a Docker volume (`/var/sewasetu/uploads`). This works for a single-node deployment but does not scale horizontally. If load balancing across multiple app containers is needed, shared storage (S3, NFS) would be required.

### No Async Processing
PDF generation now runs in < 100ms (fixed), but the entire application submission handler is still synchronous. Under extreme concurrency (thousands of simultaneous submissions), Gunicorn's 4 workers can still queue up. For month-end traffic spikes, consider increasing `workers = 8` in `gunicorn.conf` or moving PDF generation to a background task queue.

## 4. Deployment Limitations

### Admin Password
The admin password defaults to `sewasetu@123` (the original hardcoded value) unless the `ADMIN_PASSWORD` environment variable is set. This default is a known-leaked credential. **The Docker Compose file must be updated with a new password before public deployment.**

### Secret Key
The Flask secret key defaults to the value in `app.ini` (`ssp-prod-key-2023-donotshare`) unless `SECRET_KEY` env var is set. This key is in the repository and is effectively public. Any sessions signed with this key are cryptographically compromised. **Set the `SECRET_KEY` environment variable to a new random 32-byte hex string before public deployment.**

### Single Port Deployment
The application runs on a single port (8000). The SMS gateway is accessible via `/__gateway/` proxy. No separate gateway port is needed. This matches the BRIEF requirement.

## 5. Functional Gaps

### Download Links
Two PDF download links in the footer (`/downloads/beneficiary-list.pdf`, `/downloads/oap-guidelines-2023.pdf`) return 404. These files do not exist in the repository. The BRIEF does not specify what content these should contain. Placeholder files have not been added — adding content requires input from the DC's office.

### District Column
The `applications` table has no `district` column. The form captures `block` (which implies a district) but district is not stored separately. The seed data does not have a district column either. Reporting by district would require a mapping table.

### No Audit Log
Administrative actions (approve/reject) are recorded in `decided_at` and `decided_by` columns, but `decided_by` is set by the cron script only (as `'RTPS-AUTO'`) — manual admin approvals don't set `decided_by`. A proper audit trail would log which admin user performed each action. The current schema has the column but the app doesn't populate it for manual approvals.

## 6. dc-briefing.mp3

The Deputy Commissioner's audio briefing (`dc-briefing.mp3`, 3 MB) could not be transcribed in this environment — no audio-to-text tool is available. The BRIEF.md and README.md were used as authoritative requirements sources. If the audio briefing contains requirements not covered in the written brief, those are unknown and potentially unaddressed. The user should provide a transcript if available.
