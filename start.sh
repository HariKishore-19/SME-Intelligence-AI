#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/backend"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
printf '\nOpen http://localhost:8000\n'
python -m uvicorn main:app --host 127.0.0.1 --port 8000
