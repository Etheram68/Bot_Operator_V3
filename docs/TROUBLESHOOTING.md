# Guide de Dépannage - Bot Opérateur 112

## 🚨 **Problèmes Critiques**

### **1. Bot ne se connecte pas au jeu**

#### **Symptômes**
```
❌ Erreur: Impossible de naviguer vers https://www.operateur112.fr
❌ TimeoutError: Navigation timeout
❌ Login failed: Credentials rejected
```

#### **Solutions**
```bash
# 1. Vérifier les identifiants
cat .env | grep -E "USERNAME|PASSWORD"

# 2. Test manuel de connexion
python main.py --list --no-headless --debug

# 3. Vérifier la connectivité réseau
curl -I https://www.operateur112.fr

# 4. Réinitialiser la session
rm -rf ~/.playwright/  
playwright install chromium

# 5. Tester avec timeout plus long
echo "PAGE_LOAD_TIMEOUT=30" >> .env
```

#### **Causes Fréquentes**
- 🔐 **Identifiants incorrects** : Vérifier USERNAME/PASSWORD
- 🌐 **Problème réseau** : VPN, proxy, firewall
- 🔒 **Captcha/2FA** : Le jeu a activé des protections
- ⏱️ **Timeout trop court** : PAGE_LOAD_TIMEOUT < 15s
- 🤖 **Détection bot** : Le jeu bloque les automatisations

### **2. Aucun véhicule sélectionné**

#### **Symptômes**
```
📋 Besoins identifiés: {'FPT': 3, 'BEA': 1}
❌ 0 véhicules sélectionnés
❌ Échec du déploiement
```

#### **Solutions**
```bash
# 1. Analyser une mission spécifique  
python main.py --test-mission 123456 --no-headless

# 2. Vérifier les patterns de véhicules
grep -r "FPT" bot_operateur/data/needs_labels_v2.json

# 3. Analyser les conditions d'une mission
python main.py --analyze-mission 123456

# 4. Mode debug complet
python main.py --mission 123456 --debug --no-headless
```

#### **Causes Fréquentes**
- 📋 **Patterns obsolètes** : Le jeu a changé les noms de véhicules
- 🎯 **Sélecteurs DOM incorrects** : Interface jeu modifiée
- 🚫 **Tous véhicules occupés** : Aucun véhicule disponible
- ⚙️ **Configuration stricte** : VEHICLE_THRESHOLD trop bas
- 🔧 **Stratégie inadaptée** : Mauvais mapping véhicules

### **3. Performance très lente**

#### **Symptômes**
```
⏱️ Mission déployée en 45s (attendu: <5s)
🐌 Timeouts fréquents
📊 <100 missions/heure (attendu: >500)
```

#### **Solutions**
```bash
# 1. Configuration haute performance
cat > .env << EOF
HEADLESS=true
PAGE_LOAD_TIMEOUT=8
ELEMENT_WAIT_TIMEOUT=3
FAST_TIMEOUT=1
BROWSER_SLOW_MO=0
LOG_LEVEL=WARNING
EOF

# 2. Vérifier les ressources système
htop
free -h
df -h

# 3. Test benchmark
python tests/test_performance_improvements.py
```

#### **Optimisations Recommandées**
- 🖥️ **Mode headless** : `HEADLESS=true` 
- ⏱️ **Timeouts réduits** : `PAGE_LOAD_TIMEOUT=8`
- 🚀 **Slow mo désactivé** : `BROWSER_SLOW_MO=0`
- 📝 **Logs réduits** : `LOG_LEVEL=WARNING`
- 💾 **SSD recommandé** : Pour accès disque rapide

### **4. Missions skippées massivement**

#### **Symptômes**
```
🚫 Mission 123456 - trop de véhicules manquants (8 > 3)
🚫 Mission 123457 - trop de véhicules manquants (12 > 3)  
📊 0/15 missions déployées (100% skippées)
```

#### **Solutions**
```bash
# 1. Augmenter la tolérance
echo "VEHICLE_THRESHOLD=10" >> .env

# 2. Analyser les raisons de skip
python main.py --analyze-conditions --max-analyze 10

# 3. Changer de stratégie  
echo "DEFAULT_STRATEGY=balanced" >> .env

# 4. Voir les besoins détaillés
tail -f bot.log | grep -E "manquants|skip"
```

## ⚠️ **Problèmes Fréquents**

### **5. Véhicules incorrects sélectionnés**

#### **Diagnostic**
```bash
# Vérifier la stratégie active
grep DEFAULT_STRATEGY .env

# Analyser le mapping véhicules
python -c "
import json
with open('bot_operateur/data/vehicles_v2.json') as f:
    data = json.load(f)
    print(json.dumps(data['vehicle_mapping']['fire_rescue'], indent=2))
"
```

#### **Solutions**
- 🎯 **Stratégie Smart** : `DEFAULT_STRATEGY=smart`
- 📋 **Mapping à jour** : Vérifier vehicles_v2.json
- 🔄 **Patterns récents** : Mettre à jour needs_labels_v2.json

### **6. Erreurs de parsing des besoins**

#### **Symptômes**
```
⚠️ Aucun personnel reconnu dans: 6 Pompiers
⚠️ Pattern non trouvé pour: Nouveau Type Véhicule
```

#### **Solutions**
```bash
# Tester les patterns manuellement
python -c "
from bot_operateur.models.requirement_parser import RequirementParser
parser = RequirementParser()
result = parser.parse_mission_text('6 Pompiers requis')
print(result)
"

# Ajouter nouveau pattern si nécessaire
nano bot_operateur/data/needs_labels_v2.json
```

### **7. Browser crashes/zombies**

#### **Symptômes**
```
❌ BrowserContext is closed
❌ Target page, context or browser has been closed  
🧟 Processus chromium zombie
```

#### **Solutions**
```bash
# 1. Nettoyer les processus
pkill -f chromium
pkill -f "python main.py"

# 2. Réinitialiser Playwright
rm -rf ~/.playwright/
playwright install chromium

# 3. Mode recovery
python main.py --list --no-headless --timeout 60
```

## 🔧 **Diagnostics Avancés**

### **Mode Debug Complet**
```bash
# Environnement de debug
export DEBUG=1
export LOG_LEVEL=DEBUG
export HEADLESS=false

# Lancement avec logging détaillé
python main.py --mission 123456 --debug --no-headless 2>&1 | tee debug.log
```

### **Analyse des Logs**
```bash
# Erreurs critiques
grep -E "ERROR|CRITICAL" bot.log

# Timeouts et lenteurs
grep -E "timeout|slow|wait" bot.log

# Problèmes de sélection
grep -E "sélectionn|manquant|skip" bot.log

# Patterns d'erreur récurrents
awk '/ERROR/ {print $NF}' bot.log | sort | uniq -c | sort -nr
```

### **Tests de Santé du Système**
```python
# test_system_health.py
import asyncio
from bot_operateur.core.browser_manager import BrowserManager
from bot_operateur.config.settings import Settings

async def health_check():
    settings = Settings.from_env()
    browser = BrowserManager(settings)
    
    try:
        await browser.initialize()
        print("✅ Browser OK")
        
        await browser.navigate_to("https://www.operateur112.fr")
        print("✅ Game connectivity OK")
        
        # Test sélecteur critique
        elements = await browser.page.query_selector_all("div")
        print(f"✅ DOM parsing OK ({len(elements)} elements)")
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
    finally:
        await browser.cleanup()

# Exécution
asyncio.run(health_check())
```

## 📊 **Monitoring et Alertes**

### **Métriques à Surveiller**
```bash
# Performance temps réel
tail -f bot.log | grep -E "déployée|échec" | while read line; do
    echo "$(date): $line"
done

# Taux de succès
grep -c "déployée avec succès" bot.log
grep -c "Échec du déploiement" bot.log

# Temps moyen de déploiement
grep -oE "Mission.*déployée.*\([0-9.]+s\)" bot.log | \
grep -oE "[0-9.]+s" | sed 's/s//' | awk '{sum+=$1; n++} END {print sum/n "s moyenne"}'
```

### **Script de Monitoring**
```bash
#!/bin/bash
# monitor.sh

LOG_FILE="bot.log"
ALERT_THRESHOLD=5  # Seuil d'alerte (échecs consécutifs)

tail -f "$LOG_FILE" | while read line; do
    if [[ $line == *"Échec du déploiement"* ]]; then
        echo "⚠️ ALERTE: Échec détecté - $line"
        # Envoi notification (email, Slack, etc.)
    elif [[ $line == *"déployée avec succès"* ]]; then
        echo "✅ Succès: $line"  
    fi
done
```

## 🛠️ **Récupération d'Urgence**

### **Arrêt d'Urgence**
```bash
# Arrêt immédiat de tous les processus
pkill -SIGTERM -f "python main.py"
sleep 5
pkill -SIGKILL -f "python main.py"

# Nettoyage des processus browser  
pkill -f chromium
pkill -f firefox
```

### **Reset Complet**
```bash
#!/bin/bash
# reset_bot.sh

echo "🔄 Reset complet du Bot Opérateur 112..."

# 1. Arrêter tous les processus
pkill -f "python main.py"
pkill -f chromium

# 2. Nettoyer les fichiers temporaires
rm -f bot.log debug.log *.tmp
rm -rf ~/.playwright/chromium*/

# 3. Réinstaller browser
playwright install chromium

# 4. Sauvegarder/restaurer config
cp .env .env.backup
cp .env.example .env

echo "✅ Reset terminé. Reconfigurez .env et relancez."
```

### **Mode Safe**
```bash
# Configuration ultra-conservative
cat > .env.safe << EOF
USERNAME=your_username
PASSWORD=your_password
DEFAULT_STRATEGY=balanced
VEHICLE_THRESHOLD=1
HEADLESS=false
PAGE_LOAD_TIMEOUT=60
ELEMENT_WAIT_TIMEOUT=30
LOG_LEVEL=DEBUG
MAX_CONCURRENT_MISSIONS=1
EOF

# Test en mode safe
python main.py --list --config .env.safe
```

## 📞 **Support et Escalade**

### **Collecte d'Informations pour Support**
```bash
#!/bin/bash
# collect_support_info.sh

echo "=== Bot Opérateur 112 - Support Info ===" > support_info.txt
echo "Date: $(date)" >> support_info.txt
echo "" >> support_info.txt

echo "=== Environment ===" >> support_info.txt
python --version >> support_info.txt
playwright --version >> support_info.txt
cat .env | grep -v PASSWORD >> support_info.txt  # Sans mot de passe
echo "" >> support_info.txt

echo "=== Recent Logs ===" >> support_info.txt
tail -50 bot.log >> support_info.txt
echo "" >> support_info.txt

echo "=== System Info ===" >> support_info.txt
uname -a >> support_info.txt
free -h >> support_info.txt
df -h >> support_info.txt

echo "Support info collected in: support_info.txt"
```

### **Escalation Checklist**

Avant d'escalader un problème :

- [ ] ✅ **Logs consultés** : Les 100 dernières lignes de bot.log
- [ ] ✅ **Configuration vérifiée** : .env sans informations sensibles  
- [ ] ✅ **Tests de base effectués** : --list, --test-mission
- [ ] ✅ **Version confirmée** : git rev-parse HEAD
- [ ] ✅ **Reproduction** : Problème reproductible 3+ fois
- [ ] ✅ **Workaround testé** : Solutions de ce guide essayées

### **Format de Report de Bug**

```markdown
## Bug Report

**Version**: [git commit hash]
**OS**: [Windows/Linux/Mac + version]  
**Python**: [version]

**Description**:
[Description claire du problème]

**Steps to Reproduce**:
1. [Étape 1]
2. [Étape 2] 
3. [Étape 3]

**Expected**: [Comportement attendu]
**Actual**: [Comportement observé]

**Logs**: 
```
[Coller les logs pertinents ici]
```

**Configuration**:
```
[Coller .env sans PASSWORD]
```
```

**99% des problèmes sont résolus avec ce guide. Pour les 1% restants, collectez les infos de support et créez un ticket détaillé !**