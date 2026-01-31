#!/bin/bash
# Script pour extraire les statistiques du bot depuis les logs

CONTAINER_NAME="bot-operateur-112"
STATS_FILE="/usr/share/nginx/html/api/bot-stats.json"

# Vérifier si le container existe
if ! docker ps -a --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    cat > "$STATS_FILE" << 'EOF'
{
    "status": "error",
    "error": "Container not found"
}
EOF
    exit 1
fi

# Récupérer les logs récents (dernières 1000 lignes pour performance)
LOGS=$(docker logs --tail 1000 "$CONTAINER_NAME" 2>&1)

# Compter les missions déployées (recherche des patterns de succès)
MISSIONS_DEPLOYED=$(echo "$LOGS" | grep -i "mission.*déployée\|déploiement.*réussi\|deployment.*success" | wc -l)

# Compter les succès explicites
MISSIONS_SUCCESS=$(echo "$LOGS" | grep -i "succès\|success\|✅.*mission" | wc -l)

# Compter les échecs
MISSIONS_FAILED=$(echo "$LOGS" | grep -i "échec\|failed\|erreur.*mission\|❌.*mission" | wc -l)

# Compter les erreurs totales
TOTAL_ERRORS=$(echo "$LOGS" | grep -i "ERROR\|ERREUR\|Exception\|Traceback" | wc -l)

# Compter les warnings
TOTAL_WARNINGS=$(echo "$LOGS" | grep -i "WARNING\|WARN\|ATTENTION" | wc -l)

# Extraire la dernière mission déployée (timestamp approximatif)
LAST_MISSION=$(echo "$LOGS" | grep -i "mission.*déployée\|déploiement.*réussi" | tail -n 1 | head -c 150)
if [ -z "$LAST_MISSION" ]; then
    LAST_MISSION="Aucune mission récente"
fi

# Échapper les caractères JSON dans LAST_MISSION
LAST_MISSION_ESCAPED=$(echo "$LAST_MISSION" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g' | tr -d '\n\r')

# Calculer le taux de succès
if [ $MISSIONS_DEPLOYED -gt 0 ]; then
    SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", ($MISSIONS_SUCCESS / $MISSIONS_DEPLOYED) * 100}")
else
    SUCCESS_RATE="0.0"
fi

# Obtenir l'uptime du container
UPTIME_SECONDS=0
CONTAINER_STARTED=$(docker inspect -f '{{.State.StartedAt}}' "$CONTAINER_NAME" 2>/dev/null)
if [ -n "$CONTAINER_STARTED" ]; then
    START_TIMESTAMP=$(date -d "$CONTAINER_STARTED" +%s 2>/dev/null)
    CURRENT_TIMESTAMP=$(date +%s)
    if [ -n "$START_TIMESTAMP" ]; then
        UPTIME_SECONDS=$((CURRENT_TIMESTAMP - START_TIMESTAMP))
    fi
fi

# Générer le JSON
cat > "$STATS_FILE" << EOF
{
    "status": "ok",
    "missions_deployed": $MISSIONS_DEPLOYED,
    "missions_success": $MISSIONS_SUCCESS,
    "missions_failed": $MISSIONS_FAILED,
    "success_rate": $SUCCESS_RATE,
    "total_errors": $TOTAL_ERRORS,
    "total_warnings": $TOTAL_WARNINGS,
    "last_mission": "$LAST_MISSION_ESCAPED",
    "uptime_seconds": $UPTIME_SECONDS,
    "timestamp": "$(date -Iseconds)"
}
EOF
