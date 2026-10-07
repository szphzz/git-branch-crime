#!/usr/bin/env bash
# Set up a venv, run the parser tests, then scrape SFPD CompStat reports.
# Usage (from repo root):  bash scraping/run_scraper.sh [--since 2023-01] [--latest] [--upload]
set -euo pipefail
cd "$(dirname "$0")/.."

VENV=scraping/.venv   # kept inside scraping/ so it's covered by scraping/.gitignore
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"
pip install -q -r scraping/requirements.txt

python -m pytest scraping/tests -q
python -m scraping.sfpd_scraper "$@"
