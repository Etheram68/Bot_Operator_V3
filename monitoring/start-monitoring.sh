#!/bin/bash
# Script de démarrage pour le monitoring

echo "🚀 Démarrage du monitoring avec API réelle"

# Démarrer nginx en arrière-plan
echo "🌐 Démarrage de nginx..."
nginx &
NGINX_PID=$!

# Attendre que nginx démarre
sleep 2

# Démarrer le service de mise à jour API
echo "🔄 Démarrage du service de mise à jour API..."
/usr/local/bin/update-api.sh &
API_PID=$!

echo "✅ Services démarrés:"
echo "   - nginx (PID: $NGINX_PID)"
echo "   - API update service (PID: $API_PID)"

# Fonction de nettoyage
cleanup() {
    echo "🛑 Arrêt des services..."
    kill $API_PID 2>/dev/null || true
    kill $NGINX_PID 2>/dev/null || true
    exit 0
}

# Gérer les signaux d'arrêt
trap cleanup SIGTERM SIGINT

# Surveiller les processus
while true; do
    # Vérifier nginx
    if ! kill -0 $NGINX_PID 2>/dev/null; then
        echo "❌ nginx s'est arrêté, redémarrage..."
        # Arrêter tous les processus nginx avant de redémarrer
        pkill nginx 2>/dev/null || true
        sleep 2
        nginx &
        NGINX_PID=$!
    fi
    
    # Vérifier le service API
    if ! kill -0 $API_PID 2>/dev/null; then
        echo "❌ Service API s'est arrêté, redémarrage..."
        /usr/local/bin/update-api.sh &
        API_PID=$!
    fi
    
    sleep 10
done