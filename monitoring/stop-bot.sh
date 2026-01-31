#!/bin/bash
# Script pour arrêter le container bot-operateur-112

CONTAINER_NAME="bot-operateur-112"

# Vérifier si le container existe
if ! docker ps -a --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo '{"success":false,"error":"Container not found"}'
    exit 1
fi

# Arrêter le container
if docker stop "$CONTAINER_NAME" > /dev/null 2>&1; then
    echo '{"success":true,"message":"Container arrêté avec succès"}'
    exit 0
else
    echo '{"success":false,"error":"Erreur lors de l'\''arrêt"}'
    exit 1
fi
