# Amélioration : Séparation des Seuils de Véhicules

## Problème Initial

`VEHICLE_THRESHOLD` était utilisé pour **deux contextes différents** :

1. **Optimisation de sélection** : Choisir entre plusieurs petits véhicules vs un gros véhicule
2. **Décision de déploiement** : Skipper une mission si trop de véhicules manquent

Cette approche unique créait des conflits car ces deux besoins ont des exigences différentes.

## Solution Implémentée

### 🆕 Nouvelles Variables

| Variable | Usage | Défaut | Description |
|----------|-------|--------|-------------|
| `OPTIMIZATION_THRESHOLD` | Choix véhicules | 3 | Privilégier gros véhicule si >N petits |
| `DEPLOYMENT_THRESHOLD` | Skip mission | 5 | Skipper mission si >N véhicules manquent |
| `PERSONNEL_THRESHOLD` | Personnel spécialisé | 1 | Skipper si >N spécialistes manquent |

### 🔄 Compatibilité

- `VEHICLE_THRESHOLD` maintenu pour rétrocompatibilité
- Si `OPTIMIZATION_THRESHOLD` non défini → utilise `VEHICLE_THRESHOLD`
- Transition graduelle possible

## Exemples d'Usage

### Scénario 1 : Mode Performance
```bash
OPTIMIZATION_THRESHOLD=3  # Équilibré
DEPLOYMENT_THRESHOLD=8   # Tolérant = plus de missions
```

### Scénario 2 : Mode Qualité
```bash
OPTIMIZATION_THRESHOLD=2  # Strict = gros véhicules
DEPLOYMENT_THRESHOLD=3   # Strict = missions complètes
```

### Scénario 3 : Mode Vitesse (.env.speed)
```bash
OPTIMIZATION_THRESHOLD=4  # Légèrement tolérant
DEPLOYMENT_THRESHOLD=8   # Très tolérant = max missions
```

## Logique Détaillée

### Optimisation de Véhicules
```python
# Exemple : Besoin 15 pompiers
# Option A: 5x FPT (crew_size=3) = 5 véhicules
# Option B: 2x CCF(S) (crew_size=8) = 2 véhicules

if vehicle_count > OPTIMIZATION_THRESHOLD:  # 5 > 3
    # Privilégier Option B (2 véhicules)
    return "2x CCF(S)"
```

### Décision de Déploiement
```python
# Après sélection optimale : 4 trouvés, 6 manquants
if missing_count > DEPLOYMENT_THRESHOLD:  # 6 > 5
    logger.warning("🚫 Trop de véhicules manquants")
    return False  # Skip mission
```

### Personnel Spécialisé
```python
# Mission aquatique : 2x PLG manquants
if specialized_missing > PERSONNEL_THRESHOLD:  # 2 > 1
    logger.warning("🚫 Personnel critique manquant")  
    return False  # Skip mission
```

## Bénéfices

### ✅ Contrôle Granulaire
- Optimisation et déploiement configurables indépendamment
- Stratégies adaptées par environnement

### ✅ Logique Plus Intelligente
- Personnel spécialisé traité séparément (critique)
- Décisions basées sur la nature des ressources

### ✅ Flexibilité Opérationnelle
- Mode vitesse : `DEPLOYMENT_THRESHOLD=8` (tolérant)
- Mode qualité : `DEPLOYMENT_THRESHOLD=3` (strict)
- Mode équilibré : valeurs par défaut

### ✅ Maintenance
- Configuration claire et compréhensible
- Debugging facilité (logs spécifiques)
- Évolution future plus simple

## Configuration Recommandée

### Débutant (Prudent)
```bash
OPTIMIZATION_THRESHOLD=2  # Favorise gros véhicules
DEPLOYMENT_THRESHOLD=3   # Skip si beaucoup manquent
PERSONNEL_THRESHOLD=1    # Strict sur spécialistes
```

### Expérimenté (Équilibré)
```bash
OPTIMIZATION_THRESHOLD=3  # Équilibré
DEPLOYMENT_THRESHOLD=5   # Modérément tolérant
PERSONNEL_THRESHOLD=1    # Strict sur spécialistes
```

### Mode Performance (Agressif)
```bash
OPTIMIZATION_THRESHOLD=4  # Tolérant petit véhicules
DEPLOYMENT_THRESHOLD=8   # Très tolérant missions
PERSONNEL_THRESHOLD=2    # Plus tolérant spécialistes
```

## Migration

1. **Phase 1** : Ajouter nouvelles variables aux .env
2. **Phase 2** : Tester et ajuster selon comportement
3. **Phase 3** : Déprécier progressivement `VEHICLE_THRESHOLD`

L'amélioration est **rétrocompatible** et peut être adoptée graduellement.