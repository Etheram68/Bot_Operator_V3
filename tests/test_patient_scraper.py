#!/usr/bin/env python3
"""
Script de test pour vérifier le scraping des patients sur une mission spécifique
"""

import asyncio
from ..bot_operateur import OperateurBot, Settings
from ..bot_operateur.scrapers.mission_scraper import MissionScraper
from loguru import logger


async def test_patient_scraping(mission_id: str = "261032810"):
    """Test le scraping des patients sur une mission spécifique"""
    
    logger.info(f"🧪 Test du scraping des patients pour la mission {mission_id}")
    
    try:
        settings = Settings.from_env()
        
        async with OperateurBot(settings) as bot:
            page = bot.browser_manager.page
            mission_scraper = MissionScraper(page)
            
            # Tester le scraping des détails complets de la mission
            logger.info("Récupération des détails de la mission...")
            details = await mission_scraper.get_mission_details(mission_id)
            
            if details:
                patients = details.get('patients', [])
                logger.info(f"✅ Détails récupérés avec succès!")
                logger.info(f"👥 Nombre de patients trouvés: {len(patients)}")
                
                if patients:
                    logger.info("📋 Détails des patients:")
                    for i, patient in enumerate(patients):
                        needs_str = ", ".join([need.value for need in patient.needs])
                        logger.info(f"  Patient {i+1} (ID: {patient.id}):")
                        logger.info(f"    - Sévérité: {patient.severity.value}")
                        logger.info(f"    - Besoins: {needs_str}")
                else:
                    logger.warning("⚠️  Aucun patient détecté")
                    
                # Afficher aussi les autres détails
                requirements = details.get('requirements', [])
                credits = details.get('credits')
                logger.info(f"📋 Exigences trouvées: {len(requirements)}")
                if credits:
                    logger.info(f"💰 Crédits estimés: {credits}")
                    
            else:
                logger.error("❌ Impossible de récupérer les détails de la mission")
                
    except Exception as e:
        logger.error(f"❌ Erreur durant le test: {e}")
        raise


if __name__ == "__main__":
    import sys
    
    # Configuration du logging pour le test
    logger.remove()
    logger.add(sys.stdout, level="DEBUG", 
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    
    mission_id = sys.argv[1] if len(sys.argv) > 1 else "261032810"
    asyncio.run(test_patient_scraping(mission_id))