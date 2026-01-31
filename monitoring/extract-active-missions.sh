#!/bin/bash
# Script pour extraire les missions actives depuis les logs du bot

CONTAINER_NAME="bot-operateur-112"
OUTPUT_FILE="/usr/share/nginx/html/api/active-missions.json"

# Vérifier si le container existe
if ! docker ps --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    cat > "$OUTPUT_FILE" << 'EOF'
{
    "status": "error",
    "error": "Container not found",
    "missions": []
}
EOF
    exit 1
fi

# Récupérer les logs récents (dernières 500 lignes)
LOGS=$(docker logs --tail 500 "$CONTAINER_NAME" 2>&1)

# Extraire les missions en cours de traitement
# Format recherché: "Mission #12345", "Déploiement mission", etc.
MISSIONS_RAW=$(echo "$LOGS" | grep -i "mission" | grep -E "#[0-9]+|id.*[0-9]+" | tail -n 20)

# Parser les missions et créer un JSON
MISSIONS_ARRAY="[]"

if [ -n "$MISSIONS_RAW" ]; then
    # Extraire les IDs de missions uniques
    MISSION_IDS=$(echo "$MISSIONS_RAW" | grep -oE "#[0-9]+|mission.*[0-9]+" | grep -oE "[0-9]+" | sort -u | tail -n 5)

    MISSIONS_ARRAY="["
    FIRST=true

    for MISSION_ID in $MISSION_IDS; do
        # Trouver les infos de cette mission dans les logs
        MISSION_INFO=$(echo "$LOGS" | grep -i "mission.*$MISSION_ID\|#$MISSION_ID" | tail -n 3)

        # Extraire les véhicules déployés
        VEHICLES=$(echo "$MISSION_INFO" | grep -oE "[A-Z]{2,}[0-9]*|VSAV|ASSU|FPT|VIMP" | head -n 5 | tr '\n' ',' | sed 's/,$//')
        if [ -z "$VEHICLES" ]; then
            VEHICLES="En cours..."
        fi

        # Déterminer le statut
        STATUS="En cours"
        if echo "$MISSION_INFO" | grep -qi "succès\|success\|réussi\|✅"; then
            STATUS="Succès"
        elif echo "$MISSION_INFO" | grep -qi "échec\|failed\|erreur\|❌"; then
            STATUS="Échec"
        fi

        # Extraire le type de mission si disponible
        MISSION_TYPE=$(echo "$MISSION_INFO" | grep -oE "incendie|médical|accident|intervention" | head -n 1)
        if [ -z "$MISSION_TYPE" ]; then
            MISSION_TYPE="Inconnue"
        fi

        # Ajouter au tableau JSON
        if [ "$FIRST" = false ]; then
            MISSIONS_ARRAY="$MISSIONS_ARRAY,"
        fi
        FIRST=false

        # Échapper les guillemets dans les valeurs
        VEHICLES_ESC=$(echo "$VEHICLES" | sed 's/"/\\"/g')
        STATUS_ESC=$(echo "$STATUS" | sed 's/"/\\"/g')
        MISSION_TYPE_ESC=$(echo "$MISSION_TYPE" | sed 's/"/\\"/g')

        MISSIONS_ARRAY="$MISSIONS_ARRAY
        {
            \"id\": \"$MISSION_ID\",
            \"type\": \"$MISSION_TYPE_ESC\",
            \"status\": \"$STATUS_ESC\",
            \"vehicles\": \"$VEHICLES_ESC\"
        }"
    done

    MISSIONS_ARRAY="$MISSIONS_ARRAY
]"
fi

# Compter les missions actives, réussies et échouées
ACTIVE_COUNT=$(echo "$MISSIONS_ARRAY" | grep -c '"status": "En cours"')
SUCCESS_COUNT=$(echo "$MISSIONS_ARRAY" | grep -c '"status": "Succès"')
FAILED_COUNT=$(echo "$MISSIONS_ARRAY" | grep -c '"status": "Échec"')

# Générer le JSON final
cat > "$OUTPUT_FILE" << EOF
{
    "status": "ok",
    "timestamp": "$(date -Iseconds)",
    "active_count": $ACTIVE_COUNT,
    "success_count": $SUCCESS_COUNT,
    "failed_count": $FAILED_COUNT,
    "missions": $MISSIONS_ARRAY
}
EOF
