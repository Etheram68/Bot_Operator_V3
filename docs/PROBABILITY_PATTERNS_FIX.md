# Fix pour les Patterns de Probabilité

## Problème Identifié

Le système confondait les probabilités avec les besoins réels de véhicules, causant des sur-calculs dramatiques :

**Exemple concret :**
```
Mission avec :
- "Camions-citernes requis: 1" 
- "Chances qu'un camion-citerne soit requis: 50"

Résultat buggé: CITERNE: 51 (au lieu de CITERNE: 1)
```

## Cause Racine

Le pattern pour `CITERNE` incluait `"camion-citerne"` qui matchait dans la phrase de probabilité :
- ❌ **"Chances qu'un camion-citerne soit requis: 50"** → détecté comme CITERNE: 50
- ✅ **"Camions-citernes requis: 1"** → détecté comme CITERNE: 1
- **Résultat final:** CITERNE: 51 (somme des deux matches)

## Solution Implémentée

### 1. Correction du Pattern CITERNE

**Avant :**
```json
"CITERNE": ["Camions?-citernes? requis", "citernes? nécessaires?", "véhicules? citernes?", "camion-citerne"]
```

**Après :**
```json
"CITERNE": ["Camions?-citernes? requis", "citernes? nécessaires?", "véhicules? citernes?", "(?<!Chances qu'un )camion-citerne(?! soit requis)"]
```

Le pattern négatif `(?<!Chances qu'un )camion-citerne(?! soit requis)` empêche le match dans le contexte de probabilité.

### 2. Vérification des Autres Patterns

Vérification de tous les patterns susceptibles d'avoir le même problème :

| Type | Pattern Problématique | Status |
|------|---------------------|---------|
| **VAR** | `assistance respiratoire` vs `Chances qu'une assistance respiratoire soit requise` | ✅ Déjà protégé par `(?!_PROBABILITY)` |
| **VIRT** | `véhicule risques technologiques` vs `Chances qu'un véhicule risques technologiques soit requis` | ✅ Déjà protégé par `(?!_PROBABILITY)` |
| **BEA** | `Moyens élévateurs aériens` vs `Chances qu'un moyen elévateur aérien soit requise` | ✅ Pattern suffisamment spécifique |
| **CITERNE** | `camion-citerne` vs `Chances qu'un camion-citerne soit requis` | ✅ **Corrigé** |

### 3. Tests de Validation

Deux tests créés pour validation :

1. **`tests/test_citerne_probability_fix.py`** - Test spécifique CITERNE
2. **`tests/test_probability_patterns_complete.py`** - Test complet de tous les patterns

**Résultats de test :**
```
✅ CITERNE: 1 (correct) au lieu de CITERNE: 51 (bug)
✅ BEA: 2 (correct) 
✅ VAR: 1 (correct)
✅ VIRT: 1 (correct)
✅ Aucune probabilité détectée comme besoin de véhicule
```

## Architecture du Système de Probabilité

### Détecteur de Probabilités (`probability_detector.py`)

Le système utilise 3 niveaux de détection :

1. **Types de Ressources Explicites** (`_is_explicit_resource_type`)
   - `WATER_REQUIRED`, `MIN_FIREFIGHTERS`, etc.

2. **Indicateurs de Ressources Configurés** (`_is_configured_resource_indicator`)
   - Vérifie dans `needs_labels_v2.json` → `resource_indicators`

3. **Contexte de Probabilité** (`_is_probability_context`)
   - Patterns regex pour détecter "Chances qu'un X soit requis"

### Configuration JSON

```json
{
  "resource_indicators": {
    "CITERNE_PROBABILITY": "Chances qu'un camion-citerne soit requis",
    "VAR_PROBABILITY": "Chances qu'une assistance respiratoire soit requise",
    "BEA_PROBABILITY": "Chances qu'un moyen elévateur aérien soit requise"
  },
  "probability_thresholds": {
    "CITERNE_PROBABILITY": 30,
    "VAR_PROBABILITY": 25,
    "BEA_PROBABILITY": 40
  }
}
```

## Recommandations

### Pour Futurs Patterns

1. **Toujours utiliser des patterns négatifs** pour les mots-clés qui pourraient apparaître dans les probabilités :
   ```json
   "EXEMPLE": ["(?<!Chances qu'un )mot-cle(?! soit requis)"]
   ```

2. **Utiliser `(?!_PROBABILITY)`** pour les codes courts :
   ```json
   "VAR": ["\\bVAR\\b(?!_PROBABILITY)"]
   ```

3. **Tester systématiquement** avec des textes contenant probabilités et besoins réels.

### Patterns à Surveiller

Patterns susceptibles de futurs conflits :
- Tout pattern contenant des mots génériques (`véhicule`, `assistance`, `soutien`)
- Patterns courts sans délimiteurs de mots
- Patterns sans vérification de contexte

## Impact

**Avant la correction :**
- Déploiements massifs erronés (51 citernes au lieu de 1)
- Gaspillage de ressources
- Calculs de capacité d'eau incorrects

**Après la correction :**
- Détection précise des besoins réels
- Ignorance correcte des indicateurs de probabilité
- Optimisation des déploiements restaurée

## Tests de Régression

Pour éviter la réintroduction du bug :

```bash
# Test spécifique CITERNE
python tests/test_citerne_probability_fix.py

# Test complet des patterns
python tests/test_probability_patterns_complete.py
```

Les tests valident que les probabilités ne sont jamais traitées comme des besoins de véhicules.