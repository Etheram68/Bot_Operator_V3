#!/bin/bash
# Script pour vider le cache du bot

CACHE_DIR="/usr/share/nginx/html/data/cache"
CONTAINER_NAME="bot-operateur-112"

# Vider le cache via le container bot
if docker exec "$CONTAINER_NAME" sh -c "rm -rf /tmp/browser_cache/* 2>/dev/null; rm -rf /app/cache/* 2>/dev/null" > /dev/null 2>&1; then
    echo '{"success":true,"message":"Cache vidé avec succès"}'
    exit 0
else
    echo '{"success":false,"error":"Erreur lors du nettoyage du cache"}'
    exit 1
fi
