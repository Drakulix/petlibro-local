#!/usr/bin/with-contenv bashio

# Overlay fresh app files from /share if present — enables restart-only deploys
if [ -d /share/petlibro_local_app ]; then
  cp -r /share/petlibro_local_app/. /app/
fi

python3 /app/main.py
