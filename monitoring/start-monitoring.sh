#!/bin/bash
# Script de démarrage pour le monitoring

echo "🚀 Démarrage du monitoring avec API réelle"

# Démarrer le serveur API Flask en arrière-plan
echo "🐍 Démarrage du serveur API Flask..."
python3 /usr/local/bin/api-server.py &
FLASK_PID=$!

# Attendre que Flask démarre
sleep 2

# Démarrer nginx en arrière-plan
echo "🌐 Démarrage de nginx..."
nginx -g "daemon off;" &
NGINX_PID=$!

# Attendre que nginx démarre
sleep 2

# Démarrer le service de mise à jour API
echo "🔄 Démarrage du service de mise à jour API..."
/usr/local/bin/update-api.sh &
API_PID=$!

echo "✅ Services démarrés:"
echo "   - Flask API (PID: $FLASK_PID) sur port 5000"
echo "   - nginx (PID: $NGINX_PID) sur port 80"
echo "   - API update service (PID: $API_PID)"

# Fonction de nettoyage
cleanup() {
    echo "🛑 Arrêt des services..."
    kill $FLASK_PID 2>/dev/null || true
    kill $API_PID 2>/dev/null || true
    kill $NGINX_PID 2>/dev/null || true
    exit 0
}

# Gérer les signaux d'arrêt
trap cleanup SIGTERM SIGINT

# Surveiller les processus
while true; do
    # Vérifier Flask API
    if ! kill -0 $FLASK_PID 2>/dev/null; then
        echo "❌ Flask API s'est arrêté, redémarrage..."
        python3 /usr/local/bin/api-server.py &
        FLASK_PID=$!
    fi

    # Vérifier nginx
    if ! kill -0 $NGINX_PID 2>/dev/null; then
        echo "❌ nginx s'est arrêté, redémarrage..."
        # Arrêter tous les processus nginx avant de redémarrer
        pkill nginx 2>/dev/null || true
        sleep 2
        nginx -g "daemon off;" &
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