#!/bin/bash
# Debug du parsing de mémoire

echo "🧪 Debug du parsing de mémoire"
echo "==============================="

echo "1. 📊 Stats brutes du container..."
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" bot-operateur-112

echo ""
echo "2. 🔍 Parsing actuel du script..."
stats=$(docker stats --no-stream --format "table {{.Container}}\\t{{.CPUPerc}}\\t{{.MemUsage}}\\t{{.NetIO}}\\t{{.BlockIO}}" bot-operateur-112 2>/dev/null | tail -n 1)
echo "Stats complètes: $stats"

memory=$(echo "$stats" | awk '{print $3}')
echo "Colonne mémoire extraite: $memory"

memory_usage=$(echo "$memory" | cut -d'/' -f1 | sed 's/MiB/MB/g')
memory_limit=$(echo "$memory" | cut -d'/' -f2 | sed 's/MiB/MB/g')
echo "Usage parsé: $memory_usage"
echo "Limite parsée: $memory_limit"

echo ""
echo "3. 🎯 Format correct attendu..."
docker stats --no-stream --format "{{.MemUsage}}" bot-operateur-112

echo ""
echo "4. 🔧 Parsing corrigé..."
memory_raw=$(docker stats --no-stream --format "{{.MemUsage}}" bot-operateur-112)
echo "Mémoire brute: $memory_raw"

# Parser correctement
if echo "$memory_raw" | grep -q "MiB"; then
    usage=$(echo "$memory_raw" | cut -d'/' -f1 | sed 's/MiB/MB/g' | tr -d ' ')
    limit=$(echo "$memory_raw" | cut -d'/' -f2 | sed 's/MiB/MB/g' | tr -d ' ')
elif echo "$memory_raw" | grep -q "GiB"; then
    usage=$(echo "$memory_raw" | cut -d'/' -f1 | sed 's/GiB/GB/g' | tr -d ' ')
    limit=$(echo "$memory_raw" | cut -d'/' -f2 | sed 's/GiB/GB/g' | tr -d ' ')
else
    usage=$(echo "$memory_raw" | cut -d'/' -f1 | tr -d ' ')
    limit=$(echo "$memory_raw" | cut -d'/' -f2 | tr -d ' ')
fi

echo "✅ Usage corrigé: $usage"
echo "✅ Limite corrigée: $limit"

# Calculer le pourcentage
if [[ "$usage" == *"MB"* ]] && [[ "$limit" == *"MB"* ]]; then
    usage_num=$(echo "$usage" | sed 's/MB//')
    limit_num=$(echo "$limit" | sed 's/MB//')
    percentage=$(echo "scale=1; ($usage_num / $limit_num) * 100" | bc 2>/dev/null || echo "0")
    echo "📊 Pourcentage: ${percentage}%"
fi

echo ""
echo "5. 🔍 Limites définies dans docker-compose.yml..."
grep -A5 -B5 "memory:" docker-compose.yml || echo "Pas de limite trouvée"