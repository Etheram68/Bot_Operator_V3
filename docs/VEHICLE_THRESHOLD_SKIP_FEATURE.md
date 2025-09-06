# Feature VEHICLE_THRESHOLD : Skip Mission si Trop de Véhicules Manquants

## Vue d'ensemble

Cette fonctionnalité ajoute une logique intelligente pour éviter le déploiement partiel de véhicules quand trop de ressources sont manquantes. Si le nombre de véhicules manquants dépasse le seuil `VEHICLE_THRESHOLD`, la mission est automatiquement ignorée et le système passe à la mission suivante.

## Problème Résolu

**Avant :** Le système déployait parfois des véhicules même quand la majorité des besoins ne pouvaient pas être satisfaits, créant des déploiements inefficaces et des ressources gaspillées.

**Après :** Le système évalue intelligemment si le déploiement a un sens selon le nombre de véhicules manquants, et skip automatiquement les missions mal dotées en ressources.

## Configuration

### Variable d'Environnement

```bash
# Dans .env
VEHICLE_THRESHOLD=3
```

**Signification :** Si plus de 3 véhicules manquent par rapport aux besoins de la mission, ne pas déployer et passer à la mission suivante.

### Paramètre dans Settings

```python
# bot_operateur/config/settings.py
class Settings(BaseSettings):
    vehicle_threshold: int = Field(default=3, description="Seuil critique de véhicules pour forcer l'utilisation d'un véhicule plus gros")
```

## Logique de Décision

### Algorithme

```python
selected_count, missing_count = await vehicle_scraper.vehicle_needs(...)

if selected_count == -1:
    # Tous besoins déjà satisfaits
    return DEPLOY ✅
elif selected_count == 0:
    # Aucun véhicule disponible
    return SKIP ❌
elif missing_count > VEHICLE_THRESHOLD:
    # Trop de véhicules manquants
    return SKIP 🚫
else:
    # Déploiement acceptable
    return DEPLOY ✅
```

### Scénarios de Test

| Sélectionnés | Manquants | THRESHOLD=3 | Décision | Raison |
|--------------|-----------|-------------|----------|--------|
| 5 | 0 | 3 | ✅ DEPLOY | Tous véhicules trouvés |
| 4 | 2 | 3 | ✅ DEPLOY | Manquants acceptables (2 ≤ 3) |
| 3 | 3 | 3 | ✅ DEPLOY | Seuil limite (3 = 3) |
| 2 | 4 | 3 | 🚫 SKIP | Trop manquants (4 > 3) |
| 1 | 8 | 3 | 🚫 SKIP | Beaucoup trop manquants (8 > 3) |
| 0 | 10 | 3 | ❌ SKIP | Aucun disponible |
| -1 | 0 | 3 | ✅ DEPLOY | Besoins déjà satisfaits |

## Implémentation Technique

### 1. Modification `vehicle_scraper.py`

**Signature de fonction modifiée :**
```python
async def vehicle_needs(...) -> tuple[int, int]:
    """
    Returns:
        tuple[int, int]: (nombre de véhicules sélectionnés, nombre de véhicules manquants)
    """
```

**Calcul des véhicules manquants :**
```python
# Calculer le nombre de véhicules manquants
total_missing = 0
for vtype, original_needed in vehicle_needs.items():
    already_deployed = deployed_by_type.get(vtype, 0)
    selected = selected_counts.get(vtype, 0)
    total_satisfied = already_deployed + selected
    missing = max(0, original_needed - total_satisfied)
    total_missing += missing

return (final_count, total_missing)
```

### 2. Modification `mission_manager.py`

**Déballage du tuple de retour :**
```python
selected_count, missing_count = await self.vehicle_scraper.vehicle_needs(...)
```

**Vérification du seuil :**
```python
# Vérifier si trop de véhicules manquent selon le seuil VEHICLE_THRESHOLD
if missing_count > self.settings.vehicle_threshold:
    logger.warning(f"🚫 Mission {mission.id} - trop de véhicules manquants ({missing_count} > {self.settings.vehicle_threshold}). Passage à la mission suivante.")
    return False
```

## Logging et Visibilité

### Messages de Log

```
# Déploiement accepté
📊 Résumé final: 5 sélectionnés, 2 manquants
✅ Mission 12345 déployée avec succès

# Mission ignorée pour cause de manque
📊 Résumé final: 2 sélectionnés, 5 manquants  
🚫 Mission 12345 - trop de véhicules manquants (5 > 3). Passage à la mission suivante.
```

### Exemple Concret

**Mission avec besoins :**
- FPT: 3
- BEA: 2  
- CARS_POLICE: 2

**Résultat de sélection :**
- FPT: 2 sélectionnés (1 manquant)
- BEA: 0 sélectionné (2 manquants)
- CARS_POLICE: 2 sélectionnés (0 manquant)

**Total :** 4 sélectionnés, 3 manquants

**Avec VEHICLE_THRESHOLD=3 :** ✅ DEPLOY (3 = 3, acceptable)  
**Avec VEHICLE_THRESHOLD=2 :** 🚫 SKIP (3 > 2, trop manquants)

## Configuration Recommandée

### Valeurs Suggérées par Type de Déploiement

| Stratégie | VEHICLE_THRESHOLD | Usage |
|-----------|-------------------|-------|
| **Conservateur** | 1-2 | Seules missions quasi-complètes |
| **Équilibré** | 3-5 | Bon compromis efficacité/couverture |
| **Agressif** | 8-10 | Maximum de missions traitées |

### Facteurs à Considérer

- **Taille moyenne des missions** : Plus les missions sont grosses, plus le seuil peut être élevé
- **Disponibilité des véhicules** : Si peu de véhicules disponibles, seuil plus bas
- **Stratégie opérationnelle** : Priorité qualité vs quantité de missions

## Tests de Validation

```bash
# Test complet de la logique
python tests/test_vehicle_threshold_skip.py

# Résultat attendu: 7/7 tests réussis
```

## Impact sur les Performances

### Bénéfices

1. **Efficacité Améliorée** : Évite les déploiements partiels inefficaces
2. **Économie de Ressources** : Ne gaspille pas les véhicules sur des missions vouées à l'échec
3. **Meilleure Sélectivité** : Se concentre sur les missions réellement faisables

### Métriques à Surveiller

- **Taux de skip** : Missions ignorées vs missions totales
- **Taux de succès** : Missions déployées qui se terminent avec succès
- **Utilisation des ressources** : Véhicules déployés vs disponibles

## Migration et Compatibilité

### Rétrocompatibilité

✅ **Totalement compatible** - Les anciens comportements sont préservés :
- `selected_count == -1` : Tous besoins satisfaits → DEPLOY
- `selected_count == 0` : Aucun véhicule → SKIP
- Nouvelle logique s'ajoute entre les deux cas

### Configuration par Défaut

```bash
# .env.example
VEHICLE_THRESHOLD=3  # Valeur équilibrée par défaut
```

La fonctionnalité est **opt-in** via configuration et n'affecte pas les installations existantes sans modification de `.env`.

## Prochaines Améliorations Possibles

1. **VEHICLE_THRESHOLD par type** : Seuils différents selon les catégories de véhicules
2. **Seuil adaptatif** : Ajustement automatique selon les statistiques de missions
3. **Priorisation intelligente** : Facteur de priorité de mission dans la décision