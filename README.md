# GameTracker

GameTracker for self-hosted personal game tracking.

## Quick Start (Self-Host)

1. Create env file from template:
   ```bash
   cp .env.example .env
   ```
2. Set secure values in `.env`:
   - `SECRET_KEY` (long random)
   - `SUPERADMIN_PASSWORD`
   - `ALLOWED_ORIGINS` (your real frontend domain)
3. Start stack:
   ```bash
   docker compose up -d --build
   ```
4. Verify health:
   ```bash
   curl -fsS http://localhost:${BACKEND_PORT:-8000}/health
   curl -fsS http://localhost:${BACKEND_PORT:-8000}/ready
   ```

## Required Environment Variables

See [.env.example](./.env.example).

## Production Notes

- Never commit real secrets.
- Keep `ALLOWED_ORIGINS` strict.
- Expose app behind reverse proxy (TLS termination + domain).
- Rotate `SECRET_KEY` and `SUPERADMIN_PASSWORD` regularly.

## Operations

See [Self-Host Runbook](./docs/SELFHOST.md).

## Agent Build (Windows, no Docker)

Agent is built locally on Windows:

```bat
cd agent
build.bat
```

Output file:
- `agent\dist\GameTrackerAgent.exe`
