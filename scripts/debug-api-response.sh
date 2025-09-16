#!/bin/bash
# Debug de la réponse API pour identifier le problème d'affichage

echo "🔍 Debug de la réponse API pour corriger l'affichage"
echo "=================================================="

echo "1. 📡 Réponse brute de l'API stats..."
curl -s http://localhost:8081/api/container/stats | jq . 2>/dev/null || curl -s http://localhost:8081/api/container/stats

echo ""
echo "2. 📊 Extraction des valeurs spécifiques..."
response=$(curl -s http://localhost:8081/api/container/stats)

echo "Status: $(echo "$response" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)"
echo "Uptime: $(echo "$response" | grep -o '"uptime":"[^"]*"' | cut -d'"' -f4)"  
echo "CPU: $(echo "$response" | grep -o '"cpu_percent":"[^"]*"' | cut -d'"' -f4)"
echo "Memory usage: $(echo "$response" | grep -o '"memory_usage":"[^"]*"' | cut -d'"' -f4)"
echo "Memory limit: $(echo "$response" | grep -o '"memory_limit":"[^"]*"' | cut -d'"' -f4)"

echo ""
echo "3. 🎯 Format attendu par l'interface..."
echo "   - stats.status → Statut Container"
echo "   - stats.uptime → Uptime Container" 
echo "   - stats.cpu_percent → CPU Usage"
echo "   - stats.memory_usage → Mémoire Utilisée"