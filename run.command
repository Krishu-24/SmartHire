#!/usr/bin/env bash
# ============================================================
#  SmartHire launcher — macOS / Linux
#  - Verifies Python and Node are installed
#  - Creates .venv if missing; installs deps only when they change
#  - Caches the embedding model before the demo, not during it
#  - Generates the sample corpus if it isn't on disk
#  - Starts the API and the UI in ONE terminal, then opens a browser
#
#  Double-click in Finder, or run ./run.command from a terminal.
#  If double-clicking opens this in a text editor, run once:
#      chmod +x run.command
# ============================================================

set -uo pipefail

cd "$(dirname "$0")" || exit 1

API_PORT=8000
UI_PORT=5173

VENV_DIR=".venv"
VENV_PY="$VENV_DIR/bin/python"
UI_DIR="frontend"
ENV_FILE=".env"

echo "================================================"
echo "  SmartHire - Smart Shortlisting Engine"
echo "================================================"
echo

# ---- 1. Locate a Python interpreter --------------------------------
PYTHON_CMD=""
for candidate in python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_CMD="$candidate"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] Python was not found on this system."
    echo "        Install Python 3.11 or 3.12 from https://www.python.org/downloads/"
    echo "        or with Homebrew:  brew install python@3.12"
    echo
    read -r -p "Press Return to close..." _
    exit 1
fi

echo "[OK] Found Python:"
"$PYTHON_CMD" --version
echo

# ---- 2. Locate Node ------------------------------------------------
if ! command -v node >/dev/null 2>&1; then
    echo "[ERROR] Node.js was not found on this system."
    echo "        The user interface is a Vite app and needs it."
    echo "        Install the LTS build from https://nodejs.org/"
    echo "        or with Homebrew:  brew install node"
    echo
    read -r -p "Press Return to close..." _
    exit 1
fi

echo "[OK] Found Node:"
node --version
echo

# ---- 3. Virtual environment ----------------------------------------
if [ -x "$VENV_PY" ]; then
    echo "[OK] Virtual environment already exists - skipping creation."
else
    echo "[..] Creating virtual environment in .venv ..."
    if ! "$PYTHON_CMD" -m venv "$VENV_DIR"; then
        echo "[ERROR] Failed to create the virtual environment."
        echo "        Make sure the 'venv' module is available for your Python install."
        read -r -p "Press Return to close..." _
        exit 1
    fi
    echo "[OK] Virtual environment created."
fi
echo

# ---- 4. Python dependencies, only when they changed -----------------
# Compare against a copied lock rather than re-running pip every launch: on this
# dependency set a no-op pip install is still several seconds of resolver work.
LOCK_FILE="$VENV_DIR/requirements.lock"
NEED_INSTALL=1

if [ -f "$LOCK_FILE" ] && cmp -s requirements.txt "$LOCK_FILE"; then
    NEED_INSTALL=0
fi

if [ "$NEED_INSTALL" -eq 0 ]; then
    echo "[OK] Python dependencies already installed and up to date - skipping."
else
    echo "[..] Installing Python dependencies (first run pulls torch - this takes a while) ..."
    "$VENV_PY" -m pip install --upgrade pip -q
    if ! "$VENV_PY" -m pip install -r requirements.txt; then
        echo
        echo "[ERROR] Failed to install Python dependencies."
        echo "        Check your internet connection and try again."
        read -r -p "Press Return to close..." _
        exit 1
    fi
    cp requirements.txt "$LOCK_FILE"
    echo "[OK] Python dependencies installed."
fi
echo

# ---- 5. Frontend dependencies, only when they changed ---------------
UI_LOCK="$UI_DIR/node_modules/.smarthire-package.lock"
NEED_NPM=1

if [ -d "$UI_DIR/node_modules" ] && [ -f "$UI_LOCK" ] \
   && cmp -s "$UI_DIR/package.json" "$UI_LOCK"; then
    NEED_NPM=0
fi

if [ "$NEED_NPM" -eq 0 ]; then
    echo "[OK] Frontend dependencies already installed and up to date - skipping."
else
    echo "[..] Installing frontend dependencies ..."
    if ! (cd "$UI_DIR" && npm install); then
        echo
        echo "[ERROR] npm install failed."
        read -r -p "Press Return to close..." _
        exit 1
    fi
    cp "$UI_DIR/package.json" "$UI_LOCK"
    echo "[OK] Frontend dependencies installed."
fi
echo

# ---- 6. Embedding model --------------------------------------------
# A cold SentenceTransformer download mid-demo is the single most likely way
# this project fails in front of an audience. Pay it here, once, where a slow
# network is visible and recoverable rather than mysterious.
MODEL_STAMP="$VENV_DIR/model.ok"

if [ -f "$MODEL_STAMP" ]; then
    echo "[OK] Embedding model already cached - skipping warm-up."
else
    echo "[..] Caching the embedding model (first run downloads ~90MB) ..."
    if "$VENV_PY" scripts/warm_models.py; then
        echo "model cached" > "$MODEL_STAMP"
        echo "[OK] Embedding model cached and verified."
    else
        echo
        echo "[WARN] The model could not be cached or failed its sanity check."
        echo "       SmartHire will still run using the offline TF-IDF fallback,"
        echo "       with reduced semantic quality. To force it:"
        echo "           export SMARTHIRE_SEMANTIC=tfidf_svd"
        echo
    fi
fi
echo

# ---- 7. Corpus ------------------------------------------------------
if compgen -G "data/jd/*.pdf" >/dev/null 2>&1; then
    echo "[OK] Real corpus found in data/ - it will be used in preference."
elif [ -f "fixtures/synthetic/jd_technova.pdf" ]; then
    echo "[OK] Sample corpus present."
else
    echo "[..] Generating the sample corpus ..."
    if "$VENV_PY" scripts/make_synthetic_corpus.py; then
        echo "[OK] Sample corpus generated."
    else
        echo "[WARN] Could not generate the sample corpus."
        echo "       Upload a JD and resumes through the UI instead."
    fi
fi
echo

# ---- 8. Ports -------------------------------------------------------
port_busy() {
    "$VENV_PY" - "$1" <<'PY'
import socket, sys
s = socket.socket()
s.settimeout(0.4)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

check_port() {
    if port_busy "$1"; then
        echo "[ERROR] Something is already listening on port $1 ($2)."
        echo "        Close that program or the earlier SmartHire window, then re-run."
        echo "        To find it:  lsof -nP -iTCP:$1 -sTCP:LISTEN"
        echo
        read -r -p "Press Return to close..." _
        exit 1
    fi
    echo "[OK] Port $1 is free ($2)."
}

check_port "$API_PORT" "API"
check_port "$UI_PORT" "user interface"

# ---- 9. External evidence -------------------------------------------
# The token lives in .env, which .gitignore excludes. It is deliberately NOT
# stored in this script: run.command is tracked, and a credential pasted into a
# tracked file is a credential that gets committed.
if [ ! -f "$ENV_FILE" ] && [ -f ".env.example" ]; then
    cp .env.example "$ENV_FILE"
    chmod 600 "$ENV_FILE" 2>/dev/null || true
    echo "[i ] Created .env from .env.example (gitignored)."
fi

"$VENV_PY" scripts/check_token.py
TOKEN_STATE=$?

if [ "$TOKEN_STATE" -eq 2 ]; then
    echo
    # -s so the token never appears on screen or in shell history.
    read -r -s -p "Paste a GitHub token to enable live lookups (Return to skip): " WANT_TOKEN
    echo
    if [ -n "${WANT_TOKEN:-}" ]; then
        "$VENV_PY" scripts/check_token.py --save "$WANT_TOKEN"
    fi
    unset WANT_TOKEN
fi
echo

# ---- 10. Start both servers -----------------------------------------
# One terminal, not three. The API is backgrounded in THIS shell and Vite runs
# in the foreground; the trap takes the API down whatever ends the script —
# Ctrl+C, a Vite crash, or closing the window.
echo "================================================"
echo "  Starting SmartHire"
echo "    API : http://localhost:$API_PORT"
echo "    UI  : http://localhost:$UI_PORT"
echo
echo "  Press Ctrl+C to stop. Both servers run in THIS terminal."
echo "================================================"
echo

API_PID=""
shutdown() {
    if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
        echo
        echo "[..] Stopping the API ..."
        kill "$API_PID" 2>/dev/null || true
        wait "$API_PID" 2>/dev/null || true
    fi
    echo "[OK] SmartHire stopped."
}
trap shutdown EXIT INT TERM

"$VENV_PY" -m uvicorn backend.app:app --port "$API_PORT" &
API_PID=$!

echo "[..] Waiting for the API to answer ..."
READY=0
for _ in $(seq 1 40); do
    if port_busy "$API_PORT"; then
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -eq 1 ]; then
    echo "[OK] API is up."
else
    echo "[WARN] The API did not answer in time. It may still be loading the model;"
    echo "       its output appears in this terminal."
fi

# Vite binds the IPv6 loopback, so open localhost rather than 127.0.0.1 — the
# IPv4 address can refuse the connection while the server is running perfectly.
(
    sleep 3
    if command -v open >/dev/null 2>&1; then
        open "http://localhost:$UI_PORT"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://localhost:$UI_PORT" >/dev/null 2>&1
    fi
) &

(cd "$UI_DIR" && npm run dev)
