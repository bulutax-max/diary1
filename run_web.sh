#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
export FLASK_APP=src/least_used_cleanup_server.py
export FLASK_DEBUG=0
flask run --host=127.0.0.1 --port=5000
