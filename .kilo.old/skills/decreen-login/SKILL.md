---
name: decreen-login
description: >-
  Connect a Decreen account for IDE/CLI agent tools via browser PKCE login.
  Saves credentials to ~/.config/decreen/auth.json. Use when the user runs
  /decreen-login, /decreen-auth-status, /decreen-logout, or when agent auth
  is required for deepen/expand.
disable-model-invocation: true
---

# Decreen Login (Connect account)

Connect your **Decreen account** so Cursor agent tools can call authenticated APIs (`POST /architecture/expand`, workspace status, history).

**Product name:** Connect Decreen account  
**Technical:** OAuth Authorization Code + PKCE with localhost callback

## When to use

- User runs `/decreen-login`
- User runs `/decreen-auth-status` or `/decreen-logout`
- Setup before MCP or CI (optional explicit login)

## Lazy login (preferred for deepen)

`/decreen-deepen` calls the same auth helper **inline** when workspace is persistent but no token exists. Users do **not** need to run `/decreen-login` first unless they want explicit setup.

---

## Commands

### `/decreen-login`

Run browser PKCE login:

```bash
npx -y @decreen/local login
```

Monorepo / pre-publish:

```bash
node packages/decreen-local/dist/cli.js login
```

Flow:

1. Start localhost callback (`http://127.0.0.1:8479/callback`)
2. Open `${DECREEN_FRONTEND_URL}/agent/connect?...` in browser
3. User signs in (if needed)
4. Browser redirects to localhost with one-time code
5. Exchange code at `POST ${DECREEN_API}/api/v1/agent/oauth/token`
6. Save token to `~/.config/decreen/auth.json`

Tell the user:

```text
Decreen account connected.
Credentials saved locally (~/.config/decreen/auth.json).
Agent token valid for 7 days — then /decreen-deepen will lazy-login again.
Logout: npx -y @decreen/local logout
```

### `/decreen-auth-status`

```bash
npx -y @decreen/local status
```

### `/decreen-logout`

```bash
npx -y @decreen/local logout
```

---

## Credential resolution order

Shared helper: `decreen-agent-auth` (or `npx -y @decreen/local login --if-needed`) → `ensureAuthenticated()`

1. `DECREEN_AGENT_BEARER_TOKEN` env (if valid)
2. `~/.config/decreen/auth.json` (if valid)
3. Browser PKCE login (lazy or explicit)

Also accepts legacy `DECREEN_BEARER_TOKEN` env.

---

## Environment

| Variable | Default |
|----------|---------|
| `DECREEN_API` | `https://api.decreen.com` |
| `DECREEN_FRONTEND_URL` | `https://app.decreen.com` |

Local development overrides (not for published agent defaults):

| Variable | Local dev |
|----------|-----------|
| `DECREEN_API` | `http://localhost:5002` |
| `DECREEN_FRONTEND_URL` | `http://localhost:3000` |

---

## Forbidden

- Do **not** access Decreen backend infrastructure directly
- Do **not** copy session cookies from the browser manually
- Do **not** auto-claim preview workspaces during login (claim is separate)

---

## Backend endpoints

| Endpoint | Auth |
|----------|------|
| `POST /api/v1/agent/oauth/token` | Public (PKCE exchange) |
| `POST /api/v1/agent/oauth/authorize-complete` | Session (browser connect page) |
| `GET /api/v1/agent/oauth/whoami` | Bearer agent JWT |

Migration: `db/migrations/20260526_01_agent_oauth_codes.sql`
