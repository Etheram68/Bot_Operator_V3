#!/bin/bash
# Script de correction rapide

echo "🔧 Correction rapide des problèmes identifiés"
echo "============================================="

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

echo "1. 🔍 Vérification du container bot..."
if $DOCKER_COMPOSE_CMD ps | grep bot-operateur | grep -q "Up"; then
    echo "   ✅ Container bot-operateur-112 actif"
else
    echo "   ⚠️  Container bot-operateur-112 non actif - démarrage..."
    $DOCKER_COMPOSE_CMD up -d bot-operateur
fi

echo ""
echo "2. 📊 Test direct des stats du container bot..."
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" bot-operateur-112

echo ""
echo "3. ⏱️  Test de l'uptime..."
docker inspect bot-operateur-112 | grep StartedAt

echo ""
echo "4. 🔄 Redémarrage propre du monitoring..."
$DOCKER_COMPOSE_CMD restart monitoring

echo ""
echo "5. ⏳ Attente (15s) puis test API..."
sleep 15

echo ""
echo "6. 🧪 Test final de l'API stats..."
curl -s http://localhost:8081/api/container/stats | jq . 2>/dev/null || curl -s http://localhost:8081/api/container/stats

echo ""
echo "✅ Corrections appliquées !"
echo "🌐 Vérifiez maintenant : http://192.168.1.29:8081"