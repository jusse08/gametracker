# Self-Host Runbook

## 1. Pre-Production Checklist

1. Set strong secrets in `.env`:
   - `SECRET_KEY`
   - `SUPERADMIN_PASSWORD`
2. Set correct CORS:
   - `ALLOWED_ORIGINS=https://your-frontend-domain`
3. Set external API URL used by frontend build:
   - `VITE_API_BASE=https://your-api-domain/api`
4. Optional token TTL:
   - `ACCESS_TOKEN_EXPIRE_MINUTES`
5. Ensure data volume exists:
   - `./gametracker_data`

## 2. Start / Stop

Start:
```bash
docker compose up -d --build
```

Stop:
```bash
docker compose down
```

## 3. Health Monitoring

Backend health:
```bash
curl -fsS http://localhost:${BACKEND_PORT:-8000}/health
```

Backend readiness (DB check):
```bash
curl -fsS http://localhost:${BACKEND_PORT:-8000}/ready
```

Container status:
```bash
docker compose ps
```

Logs:
```bash
docker compose logs -f backend frontend
```

## 4. Backup and Restore (SQLite)

Database path (default):
- `./gametracker_data/database.db`

Backup:
```bash
mkdir -p backups
cp ./gametracker_data/database.db "./backups/database-$(date +%Y%m%d-%H%M%S).db"
```

Restore:
```bash
docker compose stop backend
cp ./backups/database-YYYYMMDD-HHMMSS.db ./gametracker_data/database.db
docker compose start backend
```

Facts file backup (optional):
```bash
cp ./gametracker_data/game_facts.json "./backups/game_facts-$(date +%Y%m%d-%H%M%S).json"
```

## 5. Update Procedure

1. Pull new version.
2. Verify `.env` has all required keys from `.env.example`.
3. Rebuild and restart:
```bash
docker compose up -d --build
```
4. Run post-update checks:
```bash
curl -fsS http://localhost:${BACKEND_PORT:-8000}/ready
docker compose ps
```

## 6. Security Baseline

1. Put reverse proxy in front (Nginx/Caddy/Traefik) with HTTPS.
2. Restrict inbound ports to only proxy entrypoints.
3. Keep Docker host and images updated.
4. Rotate secrets on schedule.
5. Use dedicated service user and firewall rules.

## 7. Failure Recovery

If backend is unhealthy:
1. Check logs: `docker compose logs backend --tail=200`
2. Check DB file permissions in `gametracker_data`.
3. Validate `.env` values.
4. Restore last known-good backup.
