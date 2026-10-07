#!/bin/bash
# SessionStart hook: install backend (Python) and frontend (npm) dependencies
# so tests and builds work in remote sessions.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Backend: venv in backend/.venv (Python 3.10+ required, 3.12 recommended).
PY=python3.12
command -v "$PY" >/dev/null 2>&1 || PY=python3
if [ ! -x backend/.venv/bin/python ]; then
  "$PY" -m venv backend/.venv
fi
backend/.venv/bin/python -m pip install --quiet --upgrade pip
backend/.venv/bin/python -m pip install --quiet -r backend/requirements.txt

# Put the venv first on PATH for the rest of the session.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export VIRTUAL_ENV=\"$CLAUDE_PROJECT_DIR/backend/.venv\"" >> "$CLAUDE_ENV_FILE"
  echo "export PATH=\"$CLAUDE_PROJECT_DIR/backend/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

# Frontend.
(cd frontend && npm install --no-audit --no-fund)
