#!/bin/sh
set -e
if [ -d /var/lib/nginx/acme ]; then
    chown nginx:nginx /var/lib/nginx/acme
    chmod 700 /var/lib/nginx/acme
fi
