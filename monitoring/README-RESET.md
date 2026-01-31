# 🗑️ Remise à zéro des patterns non reconnus

## Méthode via l'interface web

1. Accédez à l'interface de monitoring : `http://votre-ip:8081`
2. Cliquez sur le bouton **🗑️ Remettre à zéro** dans la section "Véhicules Non Reconnus"
3. Suivez les instructions affichées pour copier la commande

## Méthode manuelle via SSH

```bash
# Se connecter au QNAP
ssh admin@votre-ip-qnap

# Exécuter le script de reset dans le conteneur monitoring
docker exec bot-monitoring /usr/local/bin/reset-patterns.sh
```

## Qu'est-ce qui se passe lors du reset ?

1. ✅ Une **sauvegarde automatique** est créée avec la date/heure
2. ✅ Le fichier `unrecognized_vehicle_patterns.jsonl` est **vidé**
3. ✅ Les logs affichent la confirmation du reset
4. ✅ La sauvegarde est conservée dans `bot_operateur/data/`

## Localisation des fichiers

- **Fichier principal** : `./bot_operateur/data/unrecognized_vehicle_patterns.jsonl`
- **Sauvegardes** : `./bot_operateur/data/unrecognized_vehicle_patterns_backup_*.jsonl`
- **Script de reset** : Dans le conteneur `bot-monitoring` → `/usr/local/bin/reset-patterns.sh`

## Vérification

Après le reset, actualisez la page de monitoring. La section "Véhicules Non Reconnus" devrait afficher :

```
✅ Aucun véhicule non reconnu pour le moment
```
