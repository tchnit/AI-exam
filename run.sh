#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
exec .venv/bin/gunicorn --preload --no-control-socket --workers 2 --bind 0.0.0.0:8000 --access-logfile - --error-logfile - 'app:create_app()'
