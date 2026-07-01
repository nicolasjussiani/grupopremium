#!/bin/bash
# Install dependencies
python3 -m pip install --break-system-packages -r requirements.txt
# Run collectstatic
python3 manage.py collectstatic --noinput --clear
# Copy static files to output dir with /static/ prefix for Vercel routing
mkdir -p staticfiles_output/static
cp -r staticfiles/* staticfiles_output/static/
