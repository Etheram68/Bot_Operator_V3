# Remise à zéro des labels non reconnus

## Méthode via l'interface web

1. Accédez à l'interface de monitoring : `http://votre-ip:8081`
2. Cliquez sur le bouton **Remettre à zéro** dans la section "Labels Non Reconnus"
3. Suivez les instructions affichées pour copier la commande

## Méthode manuelle via SSH

```bash
# Se connecter au QNAP
ssh admin@votre-ip-qnap

# Exécuter le script de reset dans le conteneur monitoring
docker exec bot-monitoring /usr/local/bin/reset-patterns.sh
```

## Qu'est-ce qui se passe lors du reset ?

1. Une **sauvegarde automatique** est créée avec la date/heure
2. Le fichier `unmatched_labels.jsonl` est **vidé**
3. Les logs affichent la confirmation du reset
4. La sauvegarde est conservée dans `bot_operateur/data/`

## Localisation des fichiers

- **Fichier principal** : `./bot_operateur/data/unmatched_labels.jsonl`
- **Sauvegardes** : `./bot_operateur/data/unmatched_labels_backup_*.jsonl`
- **Script de reset** : Dans le conteneur `bot-monitoring` -> `/usr/local/bin/reset-patterns.sh`

## Sources des labels non reconnus

Le fichier `unmatched_labels.jsonl` centralise les labels de toutes les sources :

| Source | Description |
|--------|-------------|
| `table_row` | Label non reconnu dans la table d'exigences HTML (mission_scraper) |
| `vehicle_pattern` | Pattern "Il nous manque" non reconnu (mission_manager) |
| `missing_alert` | Besoin manquant non reconnu (mission_manager) |
| `missing_needs_parser` | Pattern non reconnu (missing_needs_parser) |

## Vérification

Après le reset, actualisez la page de monitoring. La section "Labels Non Reconnus" devrait afficher :

```
Aucun label non reconnu pour le moment
```
