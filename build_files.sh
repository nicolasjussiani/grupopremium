#!/bin/bash
set -euo pipefail

python3 -m pip install -r requirements.txt
python3 manage.py collectstatic --noinput --clear

mkdir -p staticfiles_output/static
cp -r staticfiles/. staticfiles_output/static/
