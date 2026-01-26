#!/usr/bin/env bash
# Start Talkie speech-assist app.

set -e
cd "$(dirname "$0")"
exec pipenv run python run.py
