#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting PRIME NICK..."
exec python main.py
