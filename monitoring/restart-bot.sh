#!/bin/bash
# Script pour redémarrer le container bot-operateur-112

CONTAINER_NAME="bot-operateur-112"

# Vérifier si le container existe
if ! docker ps -a --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo '{"success":false,"error":"Container not found"}'
    exit 1
fi

# Redémarrer le container
if docker restart "$CONTAINER_NAME" > /dev/null 2>&1; then
    echo '{"success":true,"message":"Container redémarré avec succès"}'
    exit 0
else
    echo '{"success":false,"error":"Erreur lors du redémarrage"}'
    exit 1
fi
