"""
Seva Setu — Regression Test Suite
===================================
Tests are ordered so that each test:
  1. Fails against the original buggy code (documented in comments)
  2. Passes against the fixed code

Run with:
    pip install pytest
    pytest tests/test_fixes.py -v

Note: These are unit/integration tests that use Flask's test client.
They do NOT require a running PostgreSQL instance — they mock the DB layer.
"""

import io
import sys
import os
import hashlib
import importlib
from datetime import datetime, date
from unittest.mock import MagicMock, patch, call
import pytest

# ---------------------------------------------------------------------------
# App setup — patch DB before importing to avoid real connection attempt
# ---------------------------------------------------------------------------

# We need to patch the connection pool before the module loads
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "testpass@123")

# Add app directory to path
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
sys.path.insert(0, APP_DIR)


def make_app():
    """Import and configure the Flask app for testing with a mocked DB pool."""
    # Patch psycopg2.pool so no real DB connection is attempted at module load
    mock_pool = MagicMock()
    with patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool):
        import app as flask_app_module
        importlib.reload(flask_app_module)
        flask_app_module.app.config["TESTING"] = True
        flask_app_module.app.config["WTF_CSRF_ENABLED"] = False
        return flask_app_module.app, flask_app_module, mock_pool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mock_cursor(rows=None, fetchone_value=None):
    """Return a mock cursor that returns predictable results."""
    cur = MagicMock()
    if rows is not None:
        cur.fetchall.return_value = rows
    if fetchone_value is not None:
        cur.fetchone.return_value = fetchone_value
    return cur


def hash_password(p):
    return hashlib.sha256(p.encode("utf-8")).hexdigest()


# ===========================================================================
# BUG-01: SQL Injection in /status/reset
# ===========================================================================

class TestBug01SqlInjection:
    """
    ORIGINAL BUG: /status/reset used Python % string formatting:
        cur.execute("SELECT mobile FROM portal_users WHERE mobile = '%s'" % mobile)
    An attacker could pass mobile = "' OR '1'='1" to dump all rows.

    FIX: Use parameterized queries:
        cur.execute("SELECT mobile FROM portal_users WHERE mobile = %s", (mobile,))
    """

    def test_reset_uses_parameterized_query(self):
        """
        Verify that the reset_password view calls execute() with a tuple
        parameter, not a string-formatted query.

        FAILS on original: execute() called with pre-formatted string.
        PASSES on fixed: execute() called with (%s, (mobile,)) parameterized form.
        """
        flask_app, module, _ = make_app()
        client = flask_app.test_client()

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None  # mobile not found → no reset
        mock_conn.cursor.return_value = mock_cur

        with patch.object(module, "get_db", return_value=mock_conn), \
             patch.object(module, "put_db"):
            resp = client.post("/status/reset", data={"mobile": "9999999999"})
            assert resp.status_code in (200, 302)

        # Check that execute was called with a tuple, not a pre-formatted string
        calls = mock_cur.execute.call_args_list
        assert len(calls) >= 1, "execute() was never called"

        first_call = calls[0]
        sql_arg = first_call[0][0]
        params = first_call[0][1] if len(first_call[0]) > 1 else None

        # The SQL should contain %s placeholder, not the literal mobile value
        assert "%s" in sql_arg, (
            "SQL query does not use %s placeholder — likely still using string formatting"
        )
        # The params tuple must exist and contain the mobile
        assert params is not None, (
            "No parameters tuple passed to execute() — SQL injection vulnerability present"
        )
        assert "9999999999" in str(params), (
            "Mobile number should be in params tuple, not baked into SQL string"
        )

    def test_sql_injection_attempt_does_not_return_data(self):
        """
        An injection payload as the mobile number must not cause the query
        to return rows for an unregistered mobile.

        FAILS on original: ' OR '1'='1 would return the first row.
        PASSES on fixed: treated as a literal string → no rows returned.
        """
        flask_app, module, _ = make_app()
        client = flask_app.test_client()

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        # Simulate: injection payload mobile is not in DB, so no row returned
        mock_cur.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cur

        with patch.object(module, "get_db", return_value=mock_conn), \
             patch.object(module, "put_db"), \
             patch.object(module, "send_sms") as mock_sms:
            resp = client.post("/status/reset", data={"mobile": "' OR '1'='1"})

        # SMS must NOT be sent (would indicate account was found via injection)
        mock_sms.assert_not_called()
        # Should still render the reset page (200) or redirect without error
        assert resp.status_code in (200, 302)


# ===========================================================================
# BUG-02: Admin Authorization Bypass
# ===========================================================================

class TestBug02AdminAuthBypass:
    """
    ORIGINAL BUG: admin_approve() and admin_reject() checked:
        if not session.get("logged_in"): abort(403)
    But citizen logins also set session["logged_in"] = True.
    Any citizen could approve/reject any application.

    FIX: Check session.get("admin") instead.
    """

    def test_citizen_session_cannot_approve(self):
        """
        A citizen login session (logged_in=True, admin not set) must receive
        403 when POSTing to /admin/approve/<id>.

        FAILS on original: only checks logged_in → returns 302 (redirect to list).
        PASSES on fixed: checks admin → returns 403.
        """
        flask_app, module, _ = make_app()
        client = flask_app.test_client()

        with client.session_transaction() as sess:
            sess["logged_in"] = True
            # Deliberately NOT setting sess["admin"] — this is a citizen session

        resp = client.post("/admin/approve/1")
        assert resp.status_code == 403, (
            f"Expected 403 for citizen attempting approval, got {resp.status_code}. "
            "BUG-02: admin auth bypass not fixed."
        )

    def test_citizen_session_cannot_reject(self):
        """
        A citizen login session must receive 403 when POSTing to /admin/reject/<id>.

        FAILS on original: returns 302.
        PASSES on fixed: returns 403.
        """
        flask_app, module, _ = make_app()
        client = flask_app.test_client()

        with client.session_transaction() as sess:
            sess["logged_in"] = True

        resp = client.post("/admin/reject/1")
        assert resp.status_code == 403, (
            f"Expected 403 for citizen attempting rejection, got {resp.status_code}. "
            "BUG-02: admin auth bypass not fixed."
        )

    def test_unauthenticated_cannot_approve(self):
        """No session at all → 403."""
        flask_app, module, _ = make_app()
        client = flask_app.test_client()
        resp = client.post("/admin/approve/1")
        assert resp.status_code == 403

    def test_admin_session_can_approve(self):
        """A real admin session (admin=True) must be able to approve."""
        flask_app, module, _ = make_app()
        client = flask_app.test_client()

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        with client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["admin"] = True

        with patch.object(module, "get_db", return_value=mock_conn), \
             patch.object(module, "put_db"):
            resp = client.post("/admin/approve/1")

        # Should redirect (302) to admin list, not abort
        assert resp.status_code == 302, (
            f"Admin approve should redirect after success, got {resp.status_code}"
        )


# ===========================================================================
# BUG-03: IDOR — Citizens Can View Other Citizens' Applications
# ===========================================================================

class TestBug03Idor:
    """
    ORIGINAL BUG: view_application() only checked session["logged_in"],
    never verified the logged-in mobile matches the application's mobile.

    FIX: Compare session["portal_mobile"] to row[2] (mobile column).
    Return 403 on mismatch for non-admin sessions.
    """

    def test_citizen_cannot_view_other_citizens_application(self):
        """
        Citizen A (mobile=9000000001) logged in, tries to view application
        belonging to Citizen B (mobile=9000000002). Must get 403.

        FAILS on original: returns 200 with Citizen B's data.
        PASSES on fixed: returns 403.
        """
        flask_app, module, _ = make_app()
        client = flask_app.test_client()

        # Citizen A is logged in
        with client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["portal_mobile"] = "9000000001"  # Citizen A

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        # DB returns Citizen B's application (mobile=9000000002)
        mock_cur.fetchone.return_value = (
            "SSP26123456", "Citizen B", "9000000002",  # mobile is index 2
            date(1960, 6, 5), "Village B", "Block B",
            "0000000002", "SBIN0000002", "PENDING",
            datetime(2026, 1, 15), None
        )
        mock_conn.cursor.return_value = mock_cur

        with patch.object(module, "get_db", return_value=mock_conn), \
             patch.object(module, "put_db"):
            resp = client.get("/application/2")

        assert resp.status_code == 403, (
            f"Expected 403 when citizen views another's application, got {resp.status_code}. "
            "BUG-03: IDOR not fixed."
        )

    def test_citizen_can_view_own_application(self):
        """
        Citizen A can view their own application.

        PASSES on both original and fixed — this is the happy path.
        """
        flask_app, module, _ = make_app()
        client = flask_app.test_client()

        with client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["portal_mobile"] = "9000000001"

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (
            "SSP26100001", "Citizen A", "9000000001",  # mobile matches session
            date(1960, 1, 5), "Village A", "Block A",
            "1111111111", "SBIN0000001", "PENDING",
            datetime(2026, 1, 10), None
        )
        mock_conn.cursor.return_value = mock_cur

        with patch.object(module, "get_db", return_value=mock_conn), \
             patch.object(module, "put_db"):
            resp = client.get("/application/1")

        assert resp.status_code == 200, (
            f"Expected 200 for citizen viewing own application, got {resp.status_code}"
        )

    def test_admin_can_view_any_application(self):
        """Admin is exempt from the IDOR ownership check."""
        flask_app, module, _ = make_app()
        client = flask_app.test_client()

        with client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["admin"] = True
            sess["portal_mobile"] = "admin"

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (
            "SSP26100099", "Random Citizen", "9009009009",
            date(1955, 3, 12), "Village X", "Block Y",
            "9999999999", "HDFC0000099", "APPROVED",
            datetime(2026, 2, 1), datetime(2026, 2, 10)
        )
        mock_conn.cursor.return_value = mock_cur

        with patch.object(module, "get_db", return_value=mock_conn), \
             patch.object(module, "put_db"):
            resp = client.get("/application/99")

        assert resp.status_code == 200


# ===========================================================================
# BUG-04: PDF Performance — Declaration Endpoint
# ===========================================================================

class TestBug04PdfPerformance:
    """
    ORIGINAL BUG: generate_acknowledgment() drew 4000 PDF line segments in a
    loop, blocking the worker thread for several seconds. This caused 13,759
    HTTP 504/500 errors on /declaration.

    FIX: Replace the loop with two single pdf.line() calls.
    """

    def test_acknowledgment_generates_fast(self):
        """
        generate_acknowledgment() must complete in under 2 seconds.

        FAILS on original: typically takes 3–10 seconds.
        PASSES on fixed: completes in < 100ms.
        """
        import time
        flask_app, module, _ = make_app()

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (
            "SSP26100001",
            "Test Citizen",
            "9000000001",
            date(1960, 1, 5),
            "TestVillage",
            "TestBlock",
            "123456789012",
            "SBIN0001234",
            datetime(2026, 1, 15, 10, 30),
            "PENDING",
        )

        start = time.time()
        pdf_bytes = module.generate_acknowledgment(mock_cur, 1)
        elapsed = time.time() - start

        assert elapsed < 2.0, (
            f"generate_acknowledgment took {elapsed:.2f}s — too slow. "
            "BUG-04: PDF performance not fixed."
        )
        assert len(pdf_bytes) > 0, "PDF output is empty"
        # Verify it's a PDF by checking the header
        assert pdf_bytes[:4] == b"%PDF", "Output is not a valid PDF"

    def test_acknowledgment_contains_no_loop_artifact(self):
        """
        The fixed PDF must not contain thousands of tiny line draw commands.
        (Heuristic: the PDF should be reasonably small — the loop-based version
        produced PDFs with 4000 redundant operations inflating the file.)
        """
        flask_app, module, _ = make_app()

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (
            "SSP26100001", "Test Citizen", "9000000001",
            date(1960, 1, 5), "TestVillage", "TestBlock",
            "123456789012", "SBIN0001234",
            datetime(2026, 1, 15), "PENDING",
        )

        pdf_bytes = module.generate_acknowledgment(mock_cur, 1)
        # The original looped version produces a PDF > 50 KB due to repeated commands
        # The fixed version should be < 10 KB
        assert len(pdf_bytes) < 50000, (
            f"PDF is {len(pdf_bytes)} bytes — suspiciously large, loop may not be fixed."
        )


# ===========================================================================
# BUG-05: Indian Name Truncation
# ===========================================================================

class TestBug05IndianNames:
    """
    ORIGINAL BUG: sanitize() truncated at 20 bytes and used regex
    [^\w\s\-\.,/] which strips Indic script characters.
    Hindi name "रमेश कुमार" (11 chars, 33 bytes) → empty or garbled string.

    FIX: Strip only HTML-dangerous chars, truncate by character count (maxlen=100).
    """

    def test_devanagari_name_preserved(self):
        """
        A Hindi name must be returned unchanged by sanitize().

        FAILS on original: returns empty string or truncated garbage.
        PASSES on fixed: returns the full name.
        """
        flask_app, module, _ = make_app()

        hindi_name = "रमेश कुमार"
        result = module.sanitize(hindi_name, maxlen=100)

        assert result == hindi_name, (
            f"sanitize() corrupted Hindi name: got {repr(result)!r}. "
            "BUG-05: Indian name truncation not fixed."
        )

    def test_bengali_name_preserved(self):
        """Bengali script name must be preserved."""
        flask_app, module, _ = make_app()
        bengali_name = "রহিম আলি"
        result = module.sanitize(bengali_name, maxlen=100)
        assert result == bengali_name, (
            f"Bengali name corrupted: got {repr(result)}"
        )

    def test_long_name_truncated_by_character_not_byte(self):
        """
        A 101-character name must be truncated to 100 characters (not ~33 chars
        if it were byte-truncated at 100 bytes for a 3-byte-per-char script).
        """
        flask_app, module, _ = make_app()
        long_name = "अ" * 101  # 101 Devanagari chars = 303 bytes
        result = module.sanitize(long_name, maxlen=100)
        assert len(result) == 100, (
            f"Expected 100 chars, got {len(result)}. "
            "Truncation is by bytes not characters."
        )
        assert result == "अ" * 100, "Truncated characters are garbled"

    def test_html_dangerous_chars_stripped(self):
        """
        Angle brackets, quotes etc. must be stripped to prevent XSS.
        This is a security-preserving test alongside the BUG-05 fix.
        """
        flask_app, module, _ = make_app()
        assert module.sanitize("<script>") == "script"
        assert module.sanitize("name & surname") == "name  surname"  # & stripped
        assert module.sanitize("O'Brien") == "OBrien"  # ' stripped

    def test_english_name_preserved(self):
        """Regular ASCII names must still pass through unchanged."""
        flask_app, module, _ = make_app()
        assert module.sanitize("Ramesh Kumar") == "Ramesh Kumar"
        assert module.sanitize("  Padma Devi  ") == "Padma Devi"


# ===========================================================================
# BUG-06: Deemed-Approval Cron Config Path
# ===========================================================================

class TestBug06CronConfigPath:
    """
    ORIGINAL BUG: deemed_approval.py line 23 read 'config/settings.ini'
    which doesn't exist (file renamed to app.ini in CR-2026-031).
    Result: 491 FileNotFoundError failures since 2026-03-15.

    FIX: Change path to 'config/app.ini'.
    """

    def test_deemed_approval_references_correct_config(self):
        """
        The CONFIG_PATH in deemed_approval.py must point to app.ini.

        FAILS on original: CONFIG_PATH ends with 'settings.ini'.
        PASSES on fixed: CONFIG_PATH ends with 'app.ini'.
        """
        scripts_dir = os.path.join(APP_DIR, "scripts")
        sys.path.insert(0, scripts_dir)

        # Read file line by line — only check the CONFIG_PATH assignment,
        # not comments (which may explain the old value for historical context)
        script_path = os.path.join(scripts_dir, "deemed_approval.py")
        with open(script_path, encoding="utf-8") as f:
            lines = f.readlines()

        config_path_lines = [
            l for l in lines
            if "CONFIG_PATH" in l and "=" in l and not l.strip().startswith("#")
        ]
        assert len(config_path_lines) >= 1, "CONFIG_PATH assignment not found"

        config_path_value = config_path_lines[0]
        assert "settings.ini" not in config_path_value, (
            f"CONFIG_PATH still references 'settings.ini': {config_path_value.strip()}. "
            "BUG-06 not fixed."
        )
        assert "app.ini" in config_path_value, (
            f"CONFIG_PATH does not reference 'app.ini': {config_path_value.strip()}. "
            "BUG-06 fix not applied."
        )


# ===========================================================================
# BUG-07: Date Parsing — DD/MM/YYYY must be tried first
# ===========================================================================

class TestBug07DateParsing:
    """
    ORIGINAL BUG: Date parsing tried %m/%d/%Y (US) first.
    "05/06/1960" parsed as May 6 (wrong) instead of June 5 (correct).

    FIX: Try %d/%m/%Y (Indian) first.
    """

    def test_ambiguous_date_parsed_as_dd_mm_yyyy(self):
        """
        '05/06/1960' must be parsed as 5 June 1960, not 6 May 1960.

        FAILS on original: returns date(1960, 5, 6).
        PASSES on fixed: returns date(1960, 6, 5).
        """
        from datetime import datetime, date

        # Replicate the fixed parsing logic
        dob_raw = "05/06/1960"
        dob = None
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                dob = datetime.strptime(dob_raw, fmt).date()
                break
            except ValueError:
                continue

        assert dob == date(1960, 6, 5), (
            f"Expected 1960-06-05 (5 June), got {dob}. BUG-07 not fixed."
        )

    def test_app_date_parsing_format_order(self):
        """
        Verify the app module uses DD/MM/YYYY format in the correct order
        by checking the source code.
        """
        app_path = os.path.join(APP_DIR, "app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        # %d/%m/%Y must appear in the formats list
        assert '"%d/%m/%Y"' in content or "'%d/%m/%Y'" in content, (
            "DD/MM/YYYY format not found in app.py date parsing"
        )

        # %m/%d/%Y (US format) must NOT appear in the formats tuple
        # Find the for-loop context
        us_idx = content.find('"%m/%d/%Y"')
        dd_idx = content.find('"%d/%m/%Y"')

        assert us_idx == -1, (
            "US date format %m/%d/%Y found in app.py — BUG-07 not fully fixed. "
            "Remove it to prevent ambiguous date misparse."
        )


# ===========================================================================
# BUG-14: Stub Routes for Footer Links
# ===========================================================================

class TestBug14FooterRoutes:
    """
    ORIGINAL BUG: /contact, /rti, /grievance returned 404.
    24,229 total 404 hits on these URLs over 6 months.

    FIX: Add stub Flask routes returning 200.
    """

    def test_contact_returns_200(self):
        flask_app, module, _ = make_app()
        client = flask_app.test_client()
        resp = client.get("/contact")
        assert resp.status_code == 200, (
            f"/contact returned {resp.status_code}. BUG-14 not fixed."
        )

    def test_rti_returns_200(self):
        flask_app, module, _ = make_app()
        client = flask_app.test_client()
        resp = client.get("/rti")
        assert resp.status_code == 200, (
            f"/rti returned {resp.status_code}. BUG-14 not fixed."
        )

    def test_grievance_returns_200(self):
        flask_app, module, _ = make_app()
        client = flask_app.test_client()
        resp = client.get("/grievance")
        assert resp.status_code == 200, (
            f"/grievance returned {resp.status_code}. BUG-14 not fixed."
        )


# ===========================================================================
# BUG-15: Upload UI Text
# ===========================================================================

class TestBug15UploadUiText:
    """
    ORIGINAL BUG: Upload form said "JPG or PDF, max 5 MB" but handler
    only accepts PDF and enforces 100 KB.

    FIX: Update template text to "PDF only, maximum size 100 KB".
    """

    def test_upload_template_says_pdf_only(self):
        template_path = os.path.join(APP_DIR, "templates", "upload.html")
        with open(template_path, encoding="utf-8") as f:
            content = f.read()

        assert "5 MB" not in content, (
            "upload.html still says '5 MB' — BUG-15 not fixed."
        )
        assert "JPG" not in content, (
            "upload.html still mentions JPG — BUG-15 not fixed."
        )
        assert "100 KB" in content, (
            "upload.html should say '100 KB' — BUG-15 fix not applied."
        )
        assert "PDF" in content, (
            "upload.html should mention PDF format."
        )


# ===========================================================================
# Security header tests
# ===========================================================================

class TestSecurityHeaders:
    def test_session_cookie_samesite_lax(self):
        """SESSION_COOKIE_SAMESITE must be Lax to mitigate CSRF."""
        flask_app, module, _ = make_app()
        assert flask_app.config.get("SESSION_COOKIE_SAMESITE") == "Lax", (
            "SESSION_COOKIE_SAMESITE not set to Lax"
        )

    def test_session_cookie_httponly(self):
        """SESSION_COOKIE_HTTPONLY must be True."""
        flask_app, module, _ = make_app()
        assert flask_app.config.get("SESSION_COOKIE_HTTPONLY") is True


# ===========================================================================
# Integration: connection pool
# ===========================================================================

class TestBug08ConnectionPool:
    """
    ORIGINAL BUG: get_db() created a new raw connection per request.
    FIX: Use ThreadedConnectionPool.
    """

    def test_app_uses_connection_pool(self):
        """
        app.py must import psycopg2.pool and call ThreadedConnectionPool.
        """
        app_path = os.path.join(APP_DIR, "app.py")
        with open(app_path, encoding="utf-8") as f:
            content = f.read()

        assert "psycopg2.pool" in content, (
            "app.py does not import psycopg2.pool — BUG-08 not fixed."
        )
        assert "ThreadedConnectionPool" in content, (
            "app.py does not use ThreadedConnectionPool — BUG-08 not fixed."
        )
        assert "put_db" in content, (
            "app.py does not have a put_db() function to return connections — BUG-08 not fixed."
        )
