#!/bin/bash
# Test de l'API de monitoring

echo "🧪 Test de l'API de monitoring"
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

echo "1. 🌐 Test de l'interface web principale..."
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:8081/ | head -n 3

echo ""
echo "2. 📊 Test de l'API stats..."
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:8081/api/container/stats

echo ""
echo "3. 📋 Test de l'API logs..."
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:8081/api/container/logs | head -n 5

echo ""
echo "4. 🔍 Vérification des fichiers API dans le container..."
$DOCKER_COMPOSE_CMD exec monitoring ls -la /usr/share/nginx/html/api/ 2>/dev/null || echo "❌ Impossible d'accéder au container"

echo ""
echo "5. 📂 Contenu du fichier stats.json (si existant)..."
$DOCKER_COMPOSE_CMD exec monitoring cat /usr/share/nginx/html/api/stats.json 2>/dev/null || echo "❌ Fichier stats.json non trouvé"

echo ""
echo "6. 🔧 Logs du service monitoring..."
echo "--- Dernières 10 lignes ---"
$DOCKER_COMPOSE_CMD logs monitoring --tail=10