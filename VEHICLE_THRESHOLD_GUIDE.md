# Guide VEHICLE_THRESHOLD

## Vue d'ensemble

Le `VEHICLE_THRESHOLD` est un paramètre configurable qui détermine quand le système de déploiement doit privilégier un véhicule plus gros plutôt que plusieurs véhicules plus petits.

## Comment ça marche

Quand une mission nécessite des ressources (eau ou personnel), le système :

1. **Calcule toutes les options possibles**
2. **Compte le nombre de véhicules nécessaires pour chaque option**
3. **Si une solution nécessite > VEHICLE_THRESHOLD véhicules**, il privilégie une solution avec moins de véhicules, même si elle a plus d'excédent

## Configuration

Ajoutez dans votre fichier `.env` :

```bash
# Seuil critique de véhicules (défaut: 3)
VEHICLE_THRESHOLD=3
```

## Impact des différents seuils

### Exemple : 15 pompiers nécessaires

| Seuil | Solution choisie | Excédent | Véhicules économisés |
|-------|------------------|----------|---------------------|
| 1     | 5x FS = 15       | 0        | N/A                 |
| 2     | 2x VTP(ers) = 18 | 3        | 3 véhicules         |
| **3** | **2x VTP(ers) = 18** | **3** | **3 véhicules** |
| 4     | 4x CCF(M) = 16   | 1        | 1 véhicule          |
| 5     | 5x FS = 15       | 0        | 0 véhicule          |

## Recommandations

### 🟢 VEHICLE_THRESHOLD=3 (Recommandé)
- **Bon équilibre** entre efficacité et économie de ressources
- Évite la mobilisation excessive de véhicules
- Convient à la plupart des situations

### 🟡 VEHICLE_THRESHOLD=2 (Strict)
- **Très économe** en nombre de véhicules
- Peut générer plus d'excédent
- Recommandé si les véhicules sont rares

### 🟡 VEHICLE_THRESHOLD=4-5 (Permissif)
- **Minimise l'excédent** de ressources
- Peut mobiliser plus de véhicules
- Recommandé si les véhicules sont abondants

### 🔴 VEHICLE_THRESHOLD=1 (Extrême)
- Force toujours un seul véhicule quand possible
- Peut générer beaucoup d'excédent
- Déconseillé pour un usage normal

## Cas d'usage spécifiques

### 🚒 Interventions Incendie
```bash
# Privilégier les gros porteurs d'eau
VEHICLE_THRESHOLD=2
```

### 👥 Interventions Secours à Personne
```bash
# Équilibre optimal
VEHICLE_THRESHOLD=3
```

### 🏥 Interventions Médicales Complexes
```bash
# Accepter plus de véhicules spécialisés
VEHICLE_THRESHOLD=4
```

## Test de votre configuration

Utilisez le script de test inclus :

```bash
python test_vehicle_threshold.py
```

Ce script vous montrera l'impact de différents seuils sur vos scénarios de déploiement.

## Surveillance

Le bot loggue ses décisions avec des messages comme :

```
💡 ÉCONOMIE: 3 véhicules économisés en évitant le dépassement de seuil!
```

Surveillez ces messages pour ajuster votre configuration selon vos besoins opérationnels.