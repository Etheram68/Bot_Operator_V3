#!/bin/bash
# Script pour basculer le mode debug (via redémarrage avec variable d'environnement)

CONTAINER_NAME="bot-operateur-112"
ACTION="${1:-status}"  # status, enable, disable

# Fonction pour obtenir le statut actuel du mode debug
get_debug_status() {
    # Vérifier si LOG_LEVEL=DEBUG dans les variables d'environnement
    local log_level=$(docker inspect "$CONTAINER_NAME" -f '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep "^LOG_LEVEL=" | cut -d'=' -f2)

    if [ "$log_level" = "DEBUG" ]; then
        echo "enabled"
    else
        echo "disabled"
    fi
}

case "$ACTION" in
    status)
        STATUS=$(get_debug_status)
        echo "{\"success\":true,\"debug_mode\":\"$STATUS\"}"
        ;;
    enable)
        echo '{"success":false,"message":"Mode debug nécessite un redémarrage avec LOG_LEVEL=DEBUG. Utilisez docker-compose avec la variable appropriée."}'
        ;;
    disable)
        echo '{"success":false,"message":"Désactivation du mode debug nécessite un redémarrage avec LOG_LEVEL=INFO. Utilisez docker-compose avec la variable appropriée."}'
        ;;
    *)
        echo '{"success":false,"error":"Action invalide"}'
        exit 1
        ;;
esac
