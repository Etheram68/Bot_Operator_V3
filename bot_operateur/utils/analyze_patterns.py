#!/usr/bin/env python3
"""
Analyseur de patterns de véhicules manquants non reconnus.

Ce script analyse le fichier unrecognized_vehicle_patterns.jsonl pour 
générer des statistiques et suggérer des patterns à ajouter aux fichiers JSON.
"""

import json
import os
from collections import Counter
from datetime import datetime

def analyze_patterns():
    """Analyse les patterns non reconnus et génère des statistiques."""
    
    log_file = os.path.join("data", "unrecognized_vehicle_patterns.jsonl")
    
    if not os.path.exists(log_file):
        print("❌ Aucun fichier de patterns trouvé.")
        print(f"Le fichier {log_file} sera créé automatiquement lors de la détection de nouveaux patterns.")
        return
    
    print("📊 Analyse des patterns de véhicules manquants non reconnus")
    print("=" * 60)
    
    patterns = []
    missions = set()
    
    # Lire tous les patterns
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    patterns.append(entry)
                    missions.add(entry.get("mission_id", "unknown"))
                except json.JSONDecodeError:
                    continue
    
    if not patterns:
        print("❌ Aucun pattern trouvé dans le fichier.")
        return
    
    print(f"📈 Statistiques générales:")
    print(f"   Total des patterns non reconnus: {len(patterns)}")
    print(f"   Missions concernées: {len(missions)}")
    print()
    
    # Compter les patterns les plus fréquents
    pattern_counts = Counter(entry["unrecognized_pattern"] for entry in patterns)
    
    print("🔥 Top 10 des patterns les plus fréquents:")
    for i, (pattern, count) in enumerate(pattern_counts.most_common(10), 1):
        print(f"   {i:2d}. [{count:2d}x] '{pattern}'")
    print()
    
    # Grouper par type apparent
    print("📋 Suggestions pour enrichir les fichiers JSON:")
    print("-" * 50)
    
    for pattern, count in pattern_counts.most_common():
        suggestion = suggest_mapping(pattern)
        print(f"Pattern: '{pattern}' (vu {count}x)")
        print(f"   → Suggestion: {suggestion}")
        print()
    
    # Missions récentes
    recent_patterns = sorted(patterns, key=lambda x: x["timestamp"], reverse=True)[:5]
    print("🕐 5 patterns les plus récents:")
    for entry in recent_patterns:
        timestamp = entry["timestamp"][:19]  # Garder YYYY-MM-DD HH:MM:SS
        mission_title = entry.get("mission_title", "N/A")[:30]  # Tronquer si trop long
        pattern = entry["unrecognized_pattern"]
        print(f"   {timestamp} | {mission_title:<30} | '{pattern}'")

def suggest_mapping(pattern: str) -> str:
    """Suggère un mapping possible pour un pattern donné."""
    
    pattern_lower = pattern.lower()
    
    # Suggestions basées sur des mots-clés
    suggestions = [
        (["chef", "groupe"], "CHEF_DE_GROUPE"),
        (["camion", "citerne"], "CCR"),
        (["fourgon", "incendie"], "FPT"),
        (["ambulance"], "AMBULANCE"),
        (["vsav"], "VSAV"),
        (["assu"], "ASSU"),
        (["smur"], "SMUR"),
        (["police"], "VL POLICE"),
        (["motard"], "MOTO POLICE"),
        (["vlhr"], "VLHR"),
        (["vpc"], "VPC"),
        (["dragon"], "Dragon"),
        (["hélicoptère"], "Dragon"),
        (["échelle"], "EPA"),
        (["bea"], "BEA"),
        (["ccr"], "CCR"),
        (["fpt"], "FPT"),
        (["sr"], "_SR"),
    ]
    
    for keywords, mapping in suggestions:
        if any(keyword in pattern_lower for keyword in keywords):
            return f"Probable: {mapping}"
    
    return "À analyser manuellement"

def create_sample_json_entry(pattern: str, vehicle_type: str):
    """Crée un exemple d'entrée JSON pour les fichiers de mapping."""
    
    return {
        "pattern": f"r'(\\d+)\\s*{pattern.lower()}[s]?'",
        "vehicle_type": vehicle_type,
        "note": f"Pattern ajouté depuis l'analyse automatique: '{pattern}'"
    }

if __name__ == "__main__":
    analyze_patterns()