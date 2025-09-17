#!/bin/bash
# Script pour corriger l'affichage CPU > 100%

echo "🧮 Correction de l'affichage CPU"
echo "==============================="

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

CONTAINER_NAME="bot-operateur-112"

echo "1. 📊 CPU actuel avant correction..."
cpu_before=$(docker stats --no-stream --format "{{.CPUPerc}}" $CONTAINER_NAME | sed 's/%//')
echo "CPU brut Docker: ${cpu_before}%"

echo ""
echo "2. 🔧 Limites CPU configurées..."
echo "Dans docker-compose.yml: 2.0 cores max"
echo "Donc CPU max théorique: 200%"

if (( $(echo "$cpu_before > 100" | bc -l 2>/dev/null || echo 0) )); then
    cpu_normalized=$(echo "scale=1; $cpu_before / 2" | bc 2>/dev/null)
    echo "CPU normalisé attendu: ${cpu_normalized}%"
else
    echo "CPU dans la plage normale (<100%)"
fi

echo ""
echo "3. 🔄 Application de la correction..."
$DOCKER_COMPOSE_CMD stop monitoring
$DOCKER_COMPOSE_CMD build --no-cache monitoring
$DOCKER_COMPOSE_CMD up -d monitoring

echo ""
echo "4. ⏱️  Attente génération API (20s)..."
sleep 20

echo ""
echo "5. ✅ Test après correction..."
response=$(curl -s http://localhost:8081/api/container/stats)
cpu_after=$(echo "$response" | grep -o '"cpu_percent":"[^"]*"' | cut -d'"' -f4)

echo ""
echo "📊 Résultats:"
echo "   CPU avant: ${cpu_before}%"
echo "   CPU après: ${cpu_after}%"

if (( $(echo "$cpu_after <= 100" | bc -l 2>/dev/null || echo 1) )); then
    echo "✅ CPU normalisé avec succès !"
else
    echo "⚠️  CPU encore > 100%, vérification nécessaire"
fi

echo ""
echo "6. 🧪 Vérification complète de l'API..."
echo "$response" | jq . 2>/dev/null || echo "$response"

echo ""
echo "🌐 Interface: http://192.168.1.29:8081"
echo "   → CPU Usage devrait maintenant être ≤ 100%"