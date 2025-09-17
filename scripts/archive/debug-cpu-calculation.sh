#!/bin/bash
# Debug du calcul CPU pour comprendre pourquoi > 100%

echo "🧮 Debug du calcul CPU"
echo "====================="

CONTAINER_NAME="bot-operateur-112"

echo "1. 📊 Stats CPU brutes de Docker..."
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}" $CONTAINER_NAME

echo ""
echo "2. 🔧 Limites CPU du container..."
container_id=$(docker ps --filter "name=$CONTAINER_NAME" --format "{{.ID}}")
if [ -n "$container_id" ]; then
    echo "Container ID: $container_id"
    
    # Récupérer les limites
    nano_cpus=$(docker inspect $container_id | grep -o '"NanoCpus":[0-9]*' | cut -d':' -f2)
    if [ -n "$nano_cpus" ]; then
        cpu_limit=$(echo "scale=1; $nano_cpus / 1000000000" | bc 2>/dev/null)
        echo "CPU Limit: ${cpu_limit} cores (NanoCpus: $nano_cpus)"
    else
        echo "CPU Limit: Non définie (accès à tous les cores)"
    fi
    
    # Récupérer les stats détaillées
    echo ""
    echo "3. 📈 Stats CPU détaillées..."
    docker inspect $container_id | grep -A10 -B5 "Cpu" 2>/dev/null || echo "Pas de stats CPU détaillées"
fi

echo ""
echo "4. 💻 Info système hôte..."
echo "Cores disponibles: $(nproc)"
cat /proc/loadavg 2>/dev/null || echo "Load average non disponible"

echo ""
echo "5. 🎯 Calcul théorique..."
current_cpu=$(docker stats --no-stream --format "{{.CPUPerc}}" $CONTAINER_NAME | sed 's/%//')
echo "CPU actuel Docker: ${current_cpu}%"

if [ -n "$cpu_limit" ] && [ "$cpu_limit" != "0" ]; then
    echo "Avec limite de ${cpu_limit} cores:"
    echo "  → Max théorique: $((cpu_limit * 100))%"
    if (( $(echo "$current_cpu > 100" | bc -l 2>/dev/null || echo 0) )); then
        normalized_cpu=$(echo "scale=1; $current_cpu / $cpu_limit" | bc 2>/dev/null)
        echo "  → CPU normalisé (sur 1 core): ${normalized_cpu}%"
    fi
else
    system_cores=$(nproc)
    echo "Sans limite, avec $system_cores cores système:"
    echo "  → Max théorique: $((system_cores * 100))%"
fi

echo ""
echo "6. 📊 Comparaison avec htop/top..."
echo "Top 5 processus CPU sur l'hôte:"
top -bn1 | head -n 12 | tail -n 7 2>/dev/null || echo "top non disponible"