# Authentication

MPMB-Copilot is gated behind a login. Identity lives in Postgres, passwords are hashed with argon2id, and browser sessions are server-side rows referenced by an `HttpOnly` cookie (`mpmb_session`) - only a SHA-256 hash of the session token is ever stored. Every API route except `/api/health` and `/api/auth/*` requires a signed-in user; if the database is unreachable, protected routes return 503 (fail closed).

## First run

On a fresh install no accounts exist, so the app shows a one-time **Create the admin account** screen instead of a login. The admin account manages users and settings; existing chats from before the upgrade are claimed by this account.

**Network-exposed installs (including the default Docker setup) additionally require a setup token.** When the backend starts bound to a non-loopback interface with no admin yet, it generates a one-time token and prints it to the logs:

```text
docker compose logs backend | grep setup_token_required
```

Paste that token into the setup screen's token field. This closes the window where the first visitor to an exposed fresh install could claim the admin account. Local (loopback) installs skip the token.

## Sessions

- Lifetime: 30 days absolute, 7 days idle (tunable via the `session_lifetime_days` / `session_idle_days` settings).
- Sign-out revokes the session server-side; disabling a user revokes all of theirs. Expired sessions are purged opportunistically on login.
- Login is rate-limited: 5 failed attempts per username + IP within 15 minutes returns 429.
- Passwords: minimum 10 characters, no composition rules. Login errors are deliberately uniform ("Invalid username or password").

## Database migrations

Schema changes are owned by Alembic and **run automatically at startup** once Postgres is reachable - fresh and existing installs both converge with no manual steps. Manual fallback:

```text
cd backend && uv run --no-sync alembic upgrade head
```

## HTTPS behind a reverse proxy

TLS terminates at a reverse proxy (Caddy, Traefik, nginx, or a Cloudflare Tunnel). Serve **one origin**: the built SPA at `/` and the API at `/api`, so the session cookie stays first-party. Caddy example:

```text
mpmb.example.com {
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle {
        root * /srv/frontend/dist
        try_files {path} /index.html
        file_server
    }
}
```

Two backend requirements when proxied:

1. Run uvicorn with `--proxy-headers --forwarded-allow-ips <proxy-ip>` so the backend sees the real scheme and client IP. The scheme drives the cookie's `Secure` flag (`cookie_secure=auto`); the client IP feeds login rate limiting.
2. HSTS and the HTTP-to-HTTPS redirect belong to the proxy, not the app.

Force the cookie flag regardless of detection with `COOKIE_SECURE=always` (or disable with `never` for unusual setups).

## Configuration reference

| Variable | Default | Meaning |
| --- | --- | --- |
| `BIND_HOST` | `127.0.0.1` | Must mirror uvicorn's `--host`; drives the setup-token requirement and the `AUTH_DISABLED` loopback rule. Compose sets `0.0.0.0`. |
| `AUTH_DISABLED` | `false` | Dev escape hatch: skips auth entirely. Honored **only when `BIND_HOST` is loopback** - it cannot disable auth on an exposed interface. |
| `COOKIE_SECURE` | `auto` | `auto` sets the `Secure` flag when the effective scheme is HTTPS; `always` / `never` override. |
| `session_lifetime_days` | `30` | Hot setting - absolute session lifetime. |
| `session_idle_days` | `7` | Hot setting - sliding idle timeout. |

## Development

The dev backend binds `127.0.0.1` (the Vite dev server proxies `/api` to it; LAN access to the frontend still works because the proxy runs server-side). Set `AUTH_DISABLED=true` in `.env` to skip the login during day-to-day development - by design this only works on loopback. Tests bypass the wall with a FastAPI dependency override, not this flag.

## Lost admin password

Slice 1 has a single account and no reset flow. Break-glass recovery requires database access (which implies control of the machine): orphan the chats, delete the admin row, restart, and the setup screen reappears.

```text
docker compose exec -T postgres psql -U mpmb_user -d mpmb_copilot -c "UPDATE sessions SET user_id = NULL; DELETE FROM users;"
```

Chats are not lost - orphaned sessions are claimed by the newly created admin (the claim targets only unowned chats, which is why the UPDATE comes first).
