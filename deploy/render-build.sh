#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
pip install -r requirements.txt
# Install deploy-safe AI runtime dependencies for file parsing and remote LLM calls.
pip install httpx==0.28.1 pypdf==5.1.0 "markitdown[pdf]==0.1.4"

python manage.py migrate --noinput
python manage.py collectstatic --noinput
