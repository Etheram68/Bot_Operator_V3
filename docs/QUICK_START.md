# Guide de Démarrage Rapide - Bot Opérateur 112

## 🚀 **Installation en 5 Minutes**

### **Étape 1 : Prérequis**
```bash
# Python 3.8+ requis
python --version  # Vérifier version

# Git pour cloner (optionnel si téléchargement direct)
git --version
```

### **Étape 2 : Installation**
```bash
# Aller dans le dossier du bot
cd Bot_OperateurV3

# Installer les dépendances
pip install -r requirements.txt

# Installer le navigateur
playwright install chromium
```

### **Étape 3 : Configuration**
```bash
# Copier le fichier de configuration
cp .env.example .env

# Éditer avec vos identifiants
nano .env
```

**Configurer dans `.env` :**
```bash
USERNAME=votre_nom_utilisateur_operateur112
PASSWORD=votre_mot_de_passe
DEFAULT_STRATEGY=smart
HEADLESS=true
VEHICLE_THRESHOLD=3
```

### **Étape 4 : Premier Test**
```bash
# Test de connexion (avec interface visible)
python main.py --list --no-headless

# Si OK, test en mode automatique
python main.py --auto --max-missions 2
```

## 🎯 **Commandes Essentielles**

### **Voir les missions disponibles**
```bash
python main.py --list
```

### **Déployer une mission spécifique**
```bash
python main.py --mission 123456
```

### **Mode automatique (2-5 missions)**
```bash
python main.py --auto --max-missions 3
```

### **Mode continu (24/7)**
```bash
python main.py --continuous
```

### **Mode debug (voir ce qui se passe)**
```bash
python main.py --list --no-headless --debug
```

## ⚙️ **Configuration Rapide**

### **Pour Débutants** (Sécurisé)
```bash
# .env
DEFAULT_STRATEGY=balanced
VEHICLE_THRESHOLD=2
HEADLESS=false
LOG_LEVEL=INFO
```

### **Pour Utilisateurs Expérimentés** (Rapide)
```bash
# .env  
DEFAULT_STRATEGY=smart
VEHICLE_THRESHOLD=5
HEADLESS=true
LOG_LEVEL=WARNING
PAGE_LOAD_TIMEOUT=10
```

### **Pour Farm de Crédits** (Efficace)
```bash
# .env
DEFAULT_STRATEGY=smart
MIN_CREDITS_THRESHOLD=1000
VEHICLE_THRESHOLD=3
HEADLESS=true
```

## 📊 **Résultats Attendus**

### **Performance Standard**
- ⏱️ **4.7 secondes** par mission (optimisé)  
- 🎯 **95% de succès** avec stratégie Smart
- 📈 **500-700 missions/heure** en mode continu
- 💰 **1000+ crédits/heure** selon missions

### **Exemple de Session Réussie**
```
🎯 Missions disponibles (15):
✅ Mission 123456: Incendie déployée (4.2s) - +1200 crédits
✅ Mission 123457: Accident déployée (3.8s) - +800 crédits  
✅ Mission 123458: Secours déployée (5.1s) - +600 crédits
📊 Total: 3 missions, 13.1s, +2600 crédits
```

## 🔍 **Diagnostic Rapide**

### **Problème : Connexion échoue**
```bash
# Vérifier les identifiants
cat .env | grep -E "USERNAME|PASSWORD"

# Test manuel
python main.py --list --no-headless --debug
```

### **Problème : Aucun véhicule sélectionné**
```bash
# Vérifier une mission spécifique
python main.py --test-mission 123456

# Analyser les besoins
python main.py --analyze-conditions --max-analyze 5
```

### **Problème : Performance lente**
```bash
# Configuration optimisée
echo "PAGE_LOAD_TIMEOUT=10" >> .env
echo "HEADLESS=true" >> .env
echo "BROWSER_SLOW_MO=0" >> .env
```

### **Problème : Missions skippées**
```bash
# Augmenter la tolérance
echo "VEHICLE_THRESHOLD=8" >> .env

# Vérifier les logs
tail -f bot.log | grep "🚫"
```

## 📱 **Interface et Feedback**

### **Logs Importants**
- ✅ **Mission déployée** = Succès  
- 🚫 **Mission skippée** = Pas assez de véhicules
- ❌ **Erreur** = Problème technique
- 📊 **Stats** = Performance globale

### **Codes de Retour**
- `0` = Succès total
- `1` = Erreurs partielles (certaines missions échouées)
- `2` = Erreur critique (configuration, connexion)

## 🎮 **Modes d'Usage Courants**

### **Session Courte (30 min)**
```bash
# 5-10 missions rapides
python main.py --auto --max-missions 8 --min-credits 800
```

### **Session Longue (2-3h)**  
```bash
# Mode continu avec monitoring
nohup python main.py --continuous > session.log 2>&1 &
tail -f session.log
```

### **Farm de Nuit**
```bash
# Mode 24/7 avec logging rotatif
screen -S bot_operateur
python main.py --continuous
# Ctrl+A, D pour détacher
```

## 🏆 **Optimisation Immédiate**

### **Gain de Performance Rapide**
1. **Mode headless** : `HEADLESS=true` (+30% vitesse)
2. **Timeouts réduits** : `PAGE_LOAD_TIMEOUT=10` (+25% vitesse)  
3. **Stratégie Smart** : `DEFAULT_STRATEGY=smart` (+15% efficacité)
4. **Seuil optimal** : `VEHICLE_THRESHOLD=3` (équilibre)

### **Configuration 1-Click Optimisée**
```bash
cat > .env << EOF
USERNAME=VOTRE_USERNAME
PASSWORD=VOTRE_PASSWORD
DEFAULT_STRATEGY=smart
HEADLESS=true
VEHICLE_THRESHOLD=3
PAGE_LOAD_TIMEOUT=10
ELEMENT_WAIT_TIMEOUT=5
FAST_TIMEOUT=3
LOG_LEVEL=INFO
MIN_CREDITS_THRESHOLD=800
EOF
```

## 🎯 **Objectifs Premiers Jours**

### **Jour 1 : Setup et Test**
- [ ] Installation réussie
- [ ] Connexion au jeu validée
- [ ] 3-5 missions déployées manuellement
- [ ] Configuration `.env` optimisée

### **Jour 2-3 : Automatisation** 
- [ ] Mode `--auto` maîtrisé
- [ ] 20+ missions déployées automatiquement
- [ ] Stratégie Smart adoptée
- [ ] Performance >500 missions/heure

### **Semaine 1 : Maîtrise**
- [ ] Mode `--continuous` stable
- [ ] 100+ missions déployées au total
- [ ] Configuration personnalisée affinée
- [ ] 95%+ taux de succès atteint

## 🆘 **Support d'Urgence**

### **Problème Critique**
```bash
# Arrêt d'urgence
pkill -f "python main.py"

# Réinitialisation complète
rm -f bot.log
cp .env.example .env
python main.py --list --no-headless
```

### **Contacts Support**
- 🐛 **Bug Report** : GitHub Issues
- 📖 **Documentation** : `/docs/` folder
- 💬 **Questions** : Consultez `FAQ.md`
- 🔧 **Dépannage** : Consultez `TROUBLESHOOTING.md`

## ✅ **Checklist de Validation**

Avant de considérer l'installation réussie :

- [ ] `python main.py --list` affiche des missions
- [ ] `python main.py --mission XXXXX` déploie une mission
- [ ] `python main.py --auto --max-missions 2` fonctionne
- [ ] Logs dans `bot.log` sont cohérents  
- [ ] Aucune erreur critique dans les logs
- [ ] Performance < 10s par mission

**🎉 Félicitations ! Votre Bot Opérateur 112 est prêt !**

**➡️ Étape suivante :** Consultez le [Guide Utilisateur Complet](./USER_GUIDE.md) pour maîtriser toutes les fonctionnalités avancées.