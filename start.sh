#!/bin/sh
set -e

alembic upgrade head
python main.py