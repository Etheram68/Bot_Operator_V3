#!/bin/bash
# Script pour corriger le problème d'uptime

echo "🕒 Correction du problème d'uptime"
echo "=================================="

# Détecter docker compose
DOCKER_COMPOSE_CMD=""
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
else
    echo "❌ Docker Compose non trouvé"
    exit 1
fi

echo "1. 🔍 Test direct du container status..."
container_status=$(docker ps --filter "name=bot-operateur-112" --format "{{.Status}}" 2>/dev/null)
echo "Status: $container_status"

echo ""
echo "2. 🔍 Test de jq dans le container monitoring..."
$DOCKER_COMPOSE_CMD exec monitoring which jq || echo "❌ jq non trouvé"

echo ""
echo "3. 🔍 Test direct de docker inspect..."
docker inspect bot-operateur-112 | grep "StartedAt" | head -n1

echo ""
echo "4. 📊 Test parsing d'uptime manuel..."
started_at=$(docker inspect bot-operateur-112 | grep -o '"StartedAt":"[^"]*"' | sed 's/"StartedAt":"//' | sed 's/"//' | head -n1)
echo "StartedAt extracted: $started_at"

if [ -n "$started_at" ]; then
    start_timestamp=$(date -d "$started_at" +%s 2>/dev/null)
    current_timestamp=$(date +%s)
    if [ -n "$start_timestamp" ]; then
        uptime_seconds=$((current_timestamp - start_timestamp))
        hours=$((uptime_seconds / 3600))
        minutes=$(((uptime_seconds % 3600) / 60))
        echo "✅ Uptime calculé: ${hours}h ${minutes}m (${uptime_seconds}s)"
    else
        echo "❌ Erreur parsing timestamp"
    fi
else
    echo "❌ StartedAt non trouvé"
fi

echo ""
echo "5. 🔄 Redéploiement du monitoring avec correction..."
$DOCKER_COMPOSE_CMD stop monitoring
$DOCKER_COMPOSE_CMD build --no-cache monitoring
$DOCKER_COMPOSE_CMD up -d monitoring

echo ""
echo "6. ⏱️  Attente redémarrage (15s)..."
sleep 15

echo ""
echo "7. 🧪 Test final de l'API..."
curl -s http://localhost:8081/api/container/stats | jq . 2>/dev/null || curl -s http://localhost:8081/api/container/stats

echo ""
echo "✅ Correction uptime terminée!"