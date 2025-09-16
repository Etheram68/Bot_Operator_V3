# Scripts - Guide d'utilisation

## 🚀 Scripts Principaux (À Conserver)

### `deploy-qnap.sh`
**Utilité :** Script principal de déploiement sur QNAP
- Premier déploiement du bot
- Configuration complète
- **Statut :** ✅ ESSENTIEL

### `deploy-cpu-upgrade.sh`
**Utilité :** Déploiement avec augmentation CPU + auto-reload
- Applique les améliorations de performance
- Redémarrage optimisé
- **Statut :** ✅ ESSENTIEL

### `container-api.sh`
**Utilité :** API standalone pour stats container
- Peut être utilisé indépendamment
- Référence pour debug
- **Statut :** ✅ UTILE

## 🧪 Scripts de Debug/Test (Utiles pour dépannage)

### `debug-memory.sh`
**Utilité :** Debug du parsing de mémoire
- Diagnostique les problèmes de stats
- **Statut :** ✅ CONSERVER

### `test-docker-access.sh`
**Utilité :** Test accès Docker depuis monitoring
- Diagnostique les problèmes d'API
- **Statut :** ✅ CONSERVER

### `test-monitoring-api.sh`
**Utilité :** Test complet de l'API monitoring
- Validation post-déploiement
- **Statut :** ✅ CONSERVER

## 🔧 Scripts de Correction (Ponctuels)

### `fix-api-monitoring.sh`
**Utilité :** Correction problèmes API
- Redémarrage propre monitoring
- **Statut :** ⚠️ ARCHIVER (utile mais ponctuel)

### `fix-uptime.sh`
**Utilité :** Correction spécifique uptime
- **Statut :** ⚠️ ARCHIVER (problème résolu)

### `quick-fix.sh`
**Utilité :** Correction rapide générale
- **Statut :** ⚠️ ARCHIVER (remplacé par deploy-cpu-upgrade)

## ❌ Scripts Obsolètes (À Supprimer)

### `build-no-git.sh`
**Problème :** Construction sans git (non nécessaire)
- **Statut :** ❌ SUPPRIMER

### `check-ports.sh`
**Problème :** Vérification ports (intégré dans deploy-qnap)
- **Statut :** ❌ SUPPRIMER

### `cleanup.sh`
**Problème :** Nettoyage général (redondant)
- **Statut :** ❌ SUPPRIMER

### `deploy-real-monitoring.sh`
**Problème :** Remplacé par deploy-cpu-upgrade.sh
- **Statut :** ❌ SUPPRIMER

## 📁 Organisation Recommandée

```
scripts/
├── deploy-qnap.sh              # Déploiement principal
├── deploy-cpu-upgrade.sh       # Déploiement optimisé
├── container-api.sh            # API standalone
├── debug/
│   ├── debug-memory.sh         # Debug mémoire
│   ├── test-docker-access.sh   # Test Docker
│   └── test-monitoring-api.sh  # Test API
└── archive/
    ├── fix-api-monitoring.sh   # Corrections ponctuelles
    ├── fix-uptime.sh          
    └── quick-fix.sh           
```