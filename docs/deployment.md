# Deployment Guide — Seva Setu Pension Portal

_Generated: 2026-10-19_

## Local Development (Docker Compose)

### Prerequisites
- Docker Desktop 24+ with Linux containers
- 4 GB free RAM, 2 GB free disk

### Quick Start

```bash
git clone <repository>
cd sewasetu-handout

# Start all services
docker compose up --build

# Portal: http://localhost:8000
# SMS inbox: http://localhost:8000/__gateway/
```

### Services Started by Docker Compose

| Service | Role | Port |
|---------|------|------|
| `db` | PostgreSQL 15 database | Internal only |
| `app` | Flask/Gunicorn application | 8000 |
| `scheduler` | Cron container (deemed approval at 02:00) | Internal only |
| `smsgw` | Fake SMS gateway | Internal only |

### Environment Variables (Must Set Before Production)

Set these in `docker-compose.yml` under the `app` service's `environment` section:

```yaml
environment:
  SECRET_KEY: "<32-byte random hex string — generate with: python -c \"import secrets; print(secrets.token_hex(32))\">"
  ADMIN_USERNAME: "<new admin username>"
  ADMIN_PASSWORD: "<strong random password>"
```

> [!CAUTION]
> The defaults (`SECRET_KEY = ssp-prod-key-2023-donotshare`, `ADMIN_PASSWORD = sewasetu@123`) are known-leaked values. The automated probe will test them. **You must set environment variables before public deployment.**

### Database Setup

The database is initialized automatically via `docker-entrypoint-initdb.d/` on first run. The schema (`app/schema.sql`) runs first, then the seed data (`seed/seed.sql`) loads 100,002 citizen records.

**Backup before any schema changes:**
```bash
docker compose exec db pg_dump -U sewasetu sewasetu > backup_$(date +%Y%m%d).sql
```

### Verifying the Setup

```bash
# Check all services are running
docker compose ps

# Verify app responds
curl http://localhost:8000/

# Verify SMS gateway is proxied
curl http://localhost:8000/__gateway/

# Run deemed-approval manually to clear the backlog
docker compose exec scheduler python /app/scripts/deemed_approval.py

# Check application logs
docker compose logs app

# Check cron logs
docker compose logs scheduler
```

### Admin Access

- URL: `http://localhost:8000/admin`
- Username: value of `ADMIN_USERNAME` env var (default: `admin`)
- Password: value of `ADMIN_PASSWORD` env var (default: `sewasetu@123` — **change this**)

---

## Public Deployment (Railway)

Railway is recommended because it supports Docker Compose natively and provides a free PostgreSQL add-on.

### Steps

1. **Push to GitHub:**
   ```bash
   git remote add origin https://github.com/<user>/sewasetu
   git push -u origin main
   ```

2. **Create Railway project:**
   - Go to [railway.app](https://railway.app)
   - New Project → Deploy from GitHub repo
   - Select `sewasetu-handout`

3. **Add PostgreSQL:**
   - In Railway dashboard: Add Plugin → PostgreSQL
   - Copy the `DATABASE_URL` from the PostgreSQL plugin

4. **Set environment variables in Railway:**
   ```
   SECRET_KEY = <32-byte random hex>
   ADMIN_USERNAME = <new username>
   ADMIN_PASSWORD = <strong password>
   DATABASE_URL = <from Railway PostgreSQL plugin>
   ```

5. **Update `docker-compose.yml` or create `railway.toml`** to use `DATABASE_URL` env var instead of individual DB settings.

6. **Load seed data** via Railway's PostgreSQL console or `psql`:
   ```bash
   psql $DATABASE_URL < seed/seed.sql
   ```

7. **Get public URL** from Railway dashboard (e.g., `https://sewasetu-production.up.railway.app`).

### Alternative: Render

1. Create new "Web Service" on [render.com](https://render.com)
2. Build command: `docker build -t sewasetu ./app`
3. Start command: `gunicorn -c /app/config/gunicorn.conf wsgi:app`
4. Add PostgreSQL via Render's managed database
5. Set environment variables in Render dashboard

### Alternative: fly.io

```bash
# Install flyctl
# https://fly.io/docs/hands-on/install-flyctl/

cd sewasetu-handout
fly launch          # auto-detects Dockerfile
fly postgres create # creates managed PostgreSQL
fly postgres attach # connects DB to app

fly secrets set SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
fly secrets set ADMIN_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(16))")

fly deploy
```

---

## Running Tests

```bash
# Install test dependencies
pip install pytest flask fpdf2 requests psycopg2-binary

# Run all regression tests
pytest tests/test_fixes.py -v

# Tests do NOT require a running database — they mock the DB layer
```

---

## Cron Job Verification

The deemed-approval job runs at 02:00 daily inside the `scheduler` container:

```bash
# Verify cron is scheduled
docker compose exec scheduler crontab -l

# Run manually to process the backlog
docker compose exec scheduler python /app/scripts/deemed_approval.py

# Expected output (first run after 7-month gap):
# 2026-10-20 02:00:01 deemed approval: N applications approved
```

---

## Security Checklist Before Going Live

- [ ] `SECRET_KEY` set to new random value (not the leaked default)
- [ ] `ADMIN_PASSWORD` changed from `sewasetu@123`
- [ ] PostgreSQL accessible only from internal Docker network (not publicly exposed)
- [ ] Upload directory not served as static files (documents contain PII)
- [ ] HTTPS configured on the load balancer / Railway / Render (they provide this automatically)
- [ ] Log files don't contain PII (app log redacts mobile numbers)
