#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Run Setup.command first."
  read -r -p "Press Return to close." _answer
  exit 1
fi
exec .venv/bin/python -m hiresay
