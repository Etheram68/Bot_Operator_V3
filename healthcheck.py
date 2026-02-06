#!/usr/bin/env python3
"""Healthcheck pour Docker: vérifie que le bot est actif et fonctionne."""
import sys
import time
from pathlib import Path

# Vérifier que le fichier de log existe et a été modifié récemment (< 5 min)
log_file = Path("/app/logs/bot.log")
if log_file.exists():
    last_modified = log_file.stat().st_mtime
    age_seconds = time.time() - last_modified
    if age_seconds > 300:  # 5 minutes sans log = problème
        print(f"UNHEALTHY: log inactif depuis {age_seconds:.0f}s")
        sys.exit(1)
    print(f"OK: log actif (dernière écriture il y a {age_seconds:.0f}s)")
    sys.exit(0)
else:
    # Au démarrage, le log n'existe pas encore
    print("OK: démarrage en cours")
    sys.exit(0)
