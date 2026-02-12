#!/usr/bin/env python3
"""
Analyseur de labels non reconnus.

Ce script analyse le fichier unmatched_labels.jsonl pour
générer des statistiques et suggérer des labels à ajouter à vehicle_labels.json.
"""

import json
import os
from collections import Counter
from pathlib import Path


def analyze_patterns():
    """Analyse les labels non reconnus et génère des statistiques."""

    data_dir = Path(__file__).parent.parent / "data"
    log_file = data_dir / "unmatched_labels.jsonl"

    if not os.path.exists(log_file):
        print("Aucun fichier de labels non reconnus trouvé.")
        print(f"Le fichier {log_file} sera créé automatiquement lors de la détection.")
        return

    print("Analyse des labels non reconnus")
    print("=" * 60)

    entries = []
    missions = set()

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                    missions.add(entry.get("mission_id", "unknown"))
                except json.JSONDecodeError:
                    continue

    if not entries:
        print("Aucun label non reconnu dans le fichier.")
        return

    print(f"Statistiques generales:")
    print(f"   Total labels non reconnus: {len(entries)}")
    print(f"   Missions concernees: {len(missions)}")
    print()

    # Par source
    source_counts = Counter(entry.get("source", "unknown") for entry in entries)
    print("Par source:")
    for source, count in source_counts.most_common():
        print(f"   {source}: {count}")
    print()

    # Labels les plus frequents
    label_counts = Counter(entry.get("label", entry.get("unrecognized_pattern", "?")) for entry in entries)

    print("Top 15 des labels les plus frequents:")
    for i, (label, count) in enumerate(label_counts.most_common(15), 1):
        suggestion = suggest_mapping(label)
        print(f"   {i:2d}. [{count:3d}x] '{label}'  ->  {suggestion}")
    print()

    # Suggestions pour vehicle_labels.json
    print("Suggestions pour vehicle_labels.json:")
    print("-" * 50)
    for label, count in label_counts.most_common():
        if count >= 2:  # Seulement les labels vus 2+ fois
            suggestion = suggest_mapping(label)
            normalized = label.lower().strip()
            print(f'    "{normalized}": "{suggestion}",  // vu {count}x')
    print()

    # Entries recentes
    recent = sorted(entries, key=lambda x: x.get("timestamp", ""), reverse=True)[:5]
    print("5 labels les plus recents:")
    for entry in recent:
        ts = entry.get("timestamp", "?")[:19]
        label = entry.get("label", entry.get("unrecognized_pattern", "?"))
        source = entry.get("source", "?")
        mission_id = entry.get("mission_id", "?")
        print(f"   {ts} | mission {mission_id} | [{source}] '{label}'")


def suggest_mapping(pattern: str) -> str:
    """Suggere un type de vehicule pour un label donne."""

    pattern_lower = pattern.lower()

    suggestions = [
        (["chef", "groupe"], "CHEF_DE_GROUPE"),
        (["camion", "citerne"], "CITERNE"),
        (["fourgon", "incendie"], "FPT"),
        (["ambulance"], "AMBULANCE"),
        (["vsav"], "AMBULANCE"),
        (["assu"], "AMBULANCE"),
        (["smur"], "AMBULANCE"),
        (["police", "patrouille"], "CARS_POLICE"),
        (["police"], "CARS_POLICE"),
        (["vlhr"], "VLHR"),
        (["vpc"], "VPC"),
        (["dragon"], "DRAGON"),
        (["helicoptere", "helico"], "HELICOPTER"),
        (["echelle", "bea"], "BEA"),
        (["fpt"], "FPT"),
        (["secours routier", "vsr"], "VSR"),
        (["cynophile"], "CARS_DROGUE"),
        (["drone"], "DRONE"),
    ]

    for keywords, mapping in suggestions:
        if any(keyword in pattern_lower for keyword in keywords):
            return mapping

    return "???"


if __name__ == "__main__":
    analyze_patterns()
