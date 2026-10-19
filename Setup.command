#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
echo "HireSay · first-time setup"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Install Python 3.10 or newer from python.org, then run this again."
  read -r -p "Press Return to close." _answer
  exit 1
fi
python3 -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10 or newer is required"'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
echo "Setup finished. Open Start.command to launch HireSay."
read -r -p "Press Return to close." _answer
