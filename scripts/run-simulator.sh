#!/usr/bin/env bash
# Sobe o painel em modo simulador (sem carro, sem GPS USB).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export LANCER_SOURCE="${LANCER_SOURCE:-simulator}"
if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${LANCER_PORT:-8080}"
