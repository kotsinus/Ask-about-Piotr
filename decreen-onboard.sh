#!/usr/bin/env bash
#
# decreen-onboard.sh — onboard a repo to Decreen, phase by phase.
# Portable: copy this file into any repo (or keep on PATH) and run from the repo root.
# Works on Linux, macOS, and Windows/WSL2. See docs/decreen-onboarding.md for the full guide.
#
# Usage:
#   ./decreen-onboard.sh bootstrap                 # one-time: Node (nvm) + Python venv + login shim (WSL/Linux)
#   ./decreen-onboard.sh init [WORKSPACE_ID]       # setup + login + doctor (+ pin workspace if given)
#   ./decreen-onboard.sh create                    # create a NEW workspace from latest.upload.md (preview/from-mermaid)
#   ./decreen-onboard.sh set-workspace WORKSPACE_ID# pin an existing workspace into .decreen/manifest.json
#   ./decreen-onboard.sh prepare                    # refresh --cold --prepare  (then your agent writes the map)
#   ./decreen-onboard.sh publish                    # validate + upload the map (cold direct-apply)
#   ./decreen-onboard.sh ground                     # complete --upload (coverage + source anchors)
#
# Config (override via env or edit here):
: "${DECREEN_API:=https://decreen-qa.up.railway.app}"
: "${DECREEN_FRONTEND_URL:=https://carto-prototype-qa.vercel.app}"
export DECREEN_API DECREEN_FRONTEND_URL

set -eo pipefail
# Pin the dist-tag: all published versions are prereleases (-internal.N), so an explicit
# tag resolves deterministically. If you hit a transient npm registry 404, just re-run the phase.
DECREEN="npx -y @decreen/local@latest"
RUNS=".decreen/runs"

# ---- load a usable node (nvm in WSL/Linux, else assume node on PATH) ----
load_node() {
  if [ -s "$HOME/.nvm/nvm.sh" ]; then
    export NVM_DIR="$HOME/.nvm"
    # shellcheck disable=SC1090
    set +u; . "$NVM_DIR/nvm.sh"; nvm use --lts >/dev/null 2>&1 || true; set -e
  fi
  command -v node >/dev/null 2>&1 || { echo "ERROR: node not found. Run: $0 bootstrap"; exit 1; }
  # WSL: make the Windows-browser login shim discoverable
  [ -x "$HOME/.local/bin/xdg-open" ] && export PATH="$HOME/.local/bin:$PATH"
}

cmd="${1:-help}"; shift || true

case "$cmd" in
# ---------------------------------------------------------------------------
bootstrap)
  echo ">> Node via nvm…"
  if ! [ -s "$HOME/.nvm/nvm.sh" ]; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  fi
  export NVM_DIR="$HOME/.nvm"; set +u; . "$NVM_DIR/nvm.sh"; set -e
  nvm install --lts >/dev/null; nvm use --lts >/dev/null
  echo "   node $(node -v)"

  echo ">> Python 3.12 venv for the managed runtime…"
  VENV="$HOME/.decreen/tools/cgc-kuzu/0.1.0/pyvenv"
  if [ ! -x "$VENV/bin/python" ]; then
    mkdir -p "$(dirname "$VENV")"
    if python3.12 -m venv "$VENV" 2>/dev/null && [ -x "$VENV/bin/pip" ]; then
      echo "   venv created (system ensurepip)"
    else
      # sudo-free fallback: venv without pip, then bootstrap pip
      rm -rf "$VENV"; python3.12 -m venv --without-pip "$VENV"
      curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
      "$VENV/bin/python" /tmp/get-pip.py >/dev/null
      echo "   venv created (get-pip fallback)"
    fi
  fi
  "$VENV/bin/python" -m pip --version

  if grep -qi microsoft /proc/version 2>/dev/null; then
    echo ">> WSL detected: installing xdg-open shim (opens Windows browser for login)…"
    mkdir -p "$HOME/.local/bin"
    cat > "$HOME/.local/bin/xdg-open" <<'SHIM'
#!/usr/bin/env bash
exec powershell.exe -NoProfile -Command "Start-Process '$1'"
SHIM
    chmod +x "$HOME/.local/bin/xdg-open"
  fi
  echo ">> bootstrap done."
  ;;

# ---------------------------------------------------------------------------
init)
  load_node
  # @decreen/local is a PRIVATE npm package — npm must be authenticated (with @decreen org access).
  if ! npm whoami >/dev/null 2>&1; then
    cat >&2 <<'EOF'
ERROR: npm is not authenticated, and @decreen/local is a private package.
Authenticate once (you need @decreen org access), using the SAME node/npm this script uses
(nvm-managed in WSL), then re-run `./decreen-onboard.sh init`:

  export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm use --lts
  npm login --auth-type=legacy        # terminal prompts (user / pass / OTP) — no browser needed
  #   …or set a token:  npm config set //registry.npmjs.org/:_authToken=<YOUR_NPM_TOKEN>
  npm whoami                          # must print your npm username
EOF
    exit 1
  fi
  echo ">> npm authenticated as $(npm whoami)"
  echo ">> setup…";  $DECREEN setup
  echo ">> login…";  $DECREEN login --if-needed
  echo ">> doctor…"; $DECREEN doctor --install-missing
  if [ -n "${1:-}" ]; then "$0" set-workspace "$1"; fi
  echo ">> init done."
  ;;

# ---------------------------------------------------------------------------
set-workspace)
  ws="${1:?usage: $0 set-workspace WORKSPACE_ID}"
  python3 - "$ws" "$DECREEN_FRONTEND_URL" <<'PY'
import json, os, sys
ws, frontend = sys.argv[1], sys.argv[2].rstrip('/')
p = ".decreen/manifest.json"
m = json.load(open(p)) if os.path.exists(p) else {"version": 1, "decreen": {}, "analysis": {}}
m.setdefault("decreen", {})
m["decreen"]["workspaceId"] = ws
m["decreen"]["workspaceLifecycle"] = "persistent"
m["decreen"]["workspaceUrl"] = f"{frontend}/w/{ws}/diagrams?view=facet%3Ac4"
json.dump(m, open(p, "w"), indent=2)
print(f">> manifest workspaceId -> {ws}")
PY
  ;;

# ---------------------------------------------------------------------------
create)
  # Create a NEW (temporary) workspace from a generated preview map, via from-mermaid.
  # Requires: .decreen/runs/latest.upload.md  (agent-generated: Mermaid L1/L2/L3 + ## Containment Map)
  ART="$RUNS/latest.upload.md"
  [ -f "$ART" ] || { echo "ERROR: $ART not found. Have your agent generate the preview map first."; exit 1; }
  full="$(git rev-parse --show-toplevel 2>/dev/null && true)"
  name="$(basename "${full:-$PWD}")"
  remote="$(git remote get-url origin 2>/dev/null | sed -E 's#//[^@]+@#//#' || echo '')"
  owner_repo="$(echo "$remote" | sed -E 's#.*[/:]([^/]+/[^/]+?)(\.git)?$#\1#')"; [ -n "$owner_repo" ] || owner_repo="local/$name"
  python3 - "$ART" "$owner_repo" "$(git rev-parse HEAD 2>/dev/null || echo '')" "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)" "$remote" > /tmp/decreen-from-mermaid.json <<'PY'
import json, sys
art, full, sha, branch, remote = sys.argv[1:6]
content = open(art, encoding="utf-8").read()
body = {
  "repo": {"fullName": full, "commitSha": sha, "branch": branch, "remote": remote},
  "artifact": {"format": "decreen-c4-mermaid-markdown", "content": content},
  "source": "decreen-onboard-script",
}
print(json.dumps(body))
PY
  echo ">> POST from-mermaid → $DECREEN_API …"
  resp="$(curl -sS -X POST "$DECREEN_API/api/v0/local-architecture-preview/from-mermaid" \
            -H 'Content-Type: application/json' -d @/tmp/decreen-from-mermaid.json)"
  echo "$resp" | python3 - "$DECREEN_FRONTEND_URL" <<'PY'
import json, sys
frontend = sys.argv[1].rstrip('/')
try: r = json.load(sys.stdin)
except Exception: print("Unexpected response:"); print(sys.stdin.read()); raise SystemExit(1)
wid = r.get("workspace_id"); viewer = r.get("viewer_url")
print(f">> workspace_id: {wid}")
print(f">> view now:     {viewer}")
print(f">> CLAIM (browser, makes it persistent): {frontend}/claim-preview/{wid}")
print(">> After claiming, run:  ./decreen-onboard.sh set-workspace " + str(wid) + "  then  ./decreen-onboard.sh ground")
PY
  ;;

# ---------------------------------------------------------------------------
prepare)
  load_node
  $DECREEN refresh --cold --prepare --verbose
  cat <<EOF

>> NEXT: have an AI agent (Cursor / Claude Code / Kilo) execute
     $RUNS/latest.refresh-agent-prompt.md
   and write the map to
     $RUNS/latest.refresh.upload.md
   (## Refresh Metadata + Mermaid L1/L2/L3 + ## Containment Map).
   Then run:  $0 publish
EOF
  ;;

# ---------------------------------------------------------------------------
publish)
  load_node
  [ -f "$RUNS/latest.refresh.upload.md" ] || { echo "ERROR: $RUNS/latest.refresh.upload.md missing (agent step)."; exit 1; }
  $DECREEN refresh --validate
  $DECREEN refresh --upload --direct-apply --verbose
  ;;

# ---------------------------------------------------------------------------
ground)
  load_node
  DECREEN_ACCEPT_SOURCE_ANCHORS_DISCLOSURE=1 $DECREEN complete --upload --verbose
  ;;

# ---------------------------------------------------------------------------
*)
  sed -n '2,40p' "$0"
  ;;
esac
