# Frontend toolchain versions + upgrade recommendation

Date: 2026-02-05

## 1) Versions currently used in this repo

### Next.js
- Pinned in [`frontend/package.json`](../frontend/package.json:1)
  - `next`: `16.1.6` ([`package.json`](../frontend/package.json:1))
  - `eslint-config-next`: `16.1.6` ([`package.json`](../frontend/package.json:1))

### TypeScript
- Pinned in [`frontend/package.json`](../frontend/package.json:1)
  - `typescript`: `5.5.3` ([`package.json`](../frontend/package.json:1))

### Node.js
- Docker image used by the frontend container:
  - `FROM node:20-alpine` in [`frontend/Dockerfile`](../frontend/Dockerfile:1)
    - Note: this tag pins only the *major* (`20`) and distro (`alpine`), not an exact patch release.

- Runtime minimum implied by `next@16.1.6`:
  - `next` declares `engines.node >=20.9.0` (see `node_modules/next` metadata captured in [`frontend/package-lock.json`](../frontend/package-lock.json:4395)).

### npm
- Not pinned in repo config.
  - In Docker it comes from the base Node image used in [`frontend/Dockerfile`](../frontend/Dockerfile:1).
  - Locally it depends on developers’ Node/npm installation.

## 2) Latest versions available (observed)

Based on public npm registry pages opened in the browser during this check:

- Next.js: `16.1.6` (npm shows `16.1.6` as the latest)
- TypeScript: `5.9.3` (npm shows `5.9.3` as the latest)
- npm: `11.9.0` (npm shows `11.9.0` as the latest)

Node.js:
- Recommended baseline for new work: Node `22` (LTS line)
- Latest v22.x observed from Node.js downloads index: `v22.22.0` (directory listing under `latest-v22.x`)
- Node `20` is nearing end-of-life (typical EOL for Node 20 is in 2026)

## 3) Recommendation: upgrade strategy

### Summary
- **Next.js:** already at latest (`16.1.6`) — keep as-is.
- **TypeScript:** upgrade from `5.5.3` → `5.9.3`.
- **Node.js:** upgrade the Docker base image from Node `20` → Node `22` LTS and **pin to a specific patch** (recommend `22.22.0` based on observed latest v22.x).
- **npm:** standardize npm version across dev/CI/Docker by pinning via `packageManager` in `package.json` (or accept Node-bundled npm, but document it).

### Why
1. **Reproducibility**: today you have exact dependency versions, but Node/npm are not pinned; builds can diverge between machines.
2. **Compatibility**: `next@16.1.6` requires Node `>=20.9.0` (see [`frontend/package-lock.json`](../frontend/package-lock.json:4395)), so it’s safer to explicitly set a Node baseline.
3. **Lifecycle/security**: moving to the newest LTS line (Node 22) reduces risk from upcoming Node 20 EOL.

### Concrete recommendations
1. **Pin Node in Docker**
   - Change `FROM node:20-alpine` → `FROM node:22.22.0-alpine` (exact patch), in [`frontend/Dockerfile`](../frontend/Dockerfile:1).
   - Optional: consider switching away from Alpine only if you hit native-module issues; otherwise Alpine is fine.

2. **Pin Node + npm for local dev and CI**
   - Add `engines` to [`frontend/package.json`](../frontend/package.json:1), e.g.:
     - `"engines": { "node": ">=22.0.0" }`
   - Add `packageManager` to [`frontend/package.json`](../frontend/package.json:1), e.g.:
     - `"packageManager": "npm@11.9.0"`

3. **Upgrade TypeScript**
   - Bump `typescript` `5.5.3` → `5.9.3` in [`frontend/package.json`](../frontend/package.json:1).
   - Run `npm install` to refresh [`frontend/package-lock.json`](../frontend/package-lock.json:1).

4. **Verify after upgrades**
   - Run `npm run build` and `npm run lint` in the frontend.
   - Run the app via `docker compose up --build` (see [`docker-compose.yml`](../docker-compose.yml:1)).

## 4) Decisions taken for this repo (per our discussion)

- Node.js baseline: **Node 22 LTS**
- Versioning policy: keep **exact pins** (no `^`) in [`frontend/package.json`](../frontend/package.json:1)
- Package manager: stay on **npm** and pin npm with `packageManager` (recommended `npm@11.9.0`)
