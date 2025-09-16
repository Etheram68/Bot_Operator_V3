#!/bin/bash
# Script pour tester l'accès Docker depuis le container monitoring

echo "🧪 Test d'accès Docker depuis le container monitoring"
echo "===================================================="

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

# Vérifier si le container monitoring existe
if ! $DOCKER_COMPOSE_CMD ps | grep -q "bot-monitoring"; then
    echo "❌ Container monitoring non trouvé. Démarrez-le d'abord avec:"
    echo "   $DOCKER_COMPOSE_CMD up -d monitoring"
    exit 1
fi

echo "🐳 Test de l'accès Docker depuis le container monitoring..."

# Tester l'accès docker dans le container
$DOCKER_COMPOSE_CMD exec monitoring docker ps --format "table {{.Names}}\t{{.Status}}" 2>&1

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Accès Docker OK depuis le container monitoring"
    
    # Tester spécifiquement le container bot
    echo ""
    echo "🤖 Recherche du container bot-operateur-112..."
    $DOCKER_COMPOSE_CMD exec monitoring docker ps --filter "name=bot-operateur-112" --format "table {{.Names}}\t{{.Status}}"
    
    # Tester les stats
    echo ""
    echo "📊 Test des stats Docker..."
    $DOCKER_COMPOSE_CMD exec monitoring docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" bot-operateur-112
    
else
    echo ""
    echo "❌ Accès Docker ÉCHOUÉ depuis le container monitoring"
    echo ""
    echo "🔍 Diagnostic:"
    echo "1. Vérifiez que le socket Docker est monté:"
    $DOCKER_COMPOSE_CMD exec monitoring ls -la /var/run/docker.sock
    
    echo ""
    echo "2. Vérifiez les permissions:"
    $DOCKER_COMPOSE_CMD exec monitoring stat /var/run/docker.sock
    
    echo ""
    echo "3. Vérifiez si docker CLI est installé dans le container:"
    $DOCKER_COMPOSE_CMD exec monitoring which docker
fi