#!/usr/bin/env bash
# Launch the Agent Memory Stack app.
#   • Locally: activates the `oracle_demos` conda env if present.
#   • In a Codespace / dev container: uses the system Python.
# Ensures memorizz + FastAPI are installed (from requirements.txt) before booting.
set -euo pipefail

cd "$(dirname "$0")"

# Use the oracle_demos conda env when it exists; otherwise fall back to current Python.
if command -v conda >/dev/null 2>&1 && conda env list 2>/dev/null | grep -q '/oracle_demos$\|oracle_demos '; then
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate oracle_demos
fi

# Install on first run, and upgrade an older MemoRizz rather than accepting an
# importable-but-incompatible pre-0.6 package.
python -c 'from importlib.metadata import version; import fastapi, sse_starlette; assert version("memorizz").split(".")[:2] == ["0", "6"]' 2>/dev/null \
  || python -m pip install -q -r requirements.txt

HOST="${HOST:-127.0.0.1}"   # devcontainer sets HOST=0.0.0.0 for port forwarding
PORT="${PORT:-8000}"
echo "→ Agent Memory Stack on http://${HOST}:${PORT}"
exec uvicorn backend.main:app --host "${HOST}" --port "${PORT}" "$@"
