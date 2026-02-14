"""
Service de gestion des transports (patients et prisonniers).
Extrait de MissionManager pour une architecture modulaire.
"""

import re
from loguru import logger
from playwright.async_api import Page


class TransportService:
    """Gère les transports sanitaires et de prisonniers pour les missions."""

    def __init__(self, page: Page):
        self.page = page

    async def handle_patient_transport_initial(self, mission) -> bool:
        """
        Gère automatiquement les demandes de transport (patients/prisonniers) en début de mission.

        Détecte et traite les alertes de transport avant de lire les conditions,
        supportant à la fois les transports sanitaires et les transports de prisonniers.
        """
        logger.info(f"🚑 Vérification des transports initiaux pour mission {mission.title} ({mission.id})")

        try:
            # Vérifier d'abord si la mission est accomplie
            mission_complete = await self.page.query_selector(".mission-success")
            if mission_complete:
                logger.info(f"🏁 Mission {mission.id} déjà accomplie - aucun transport nécessaire")
                return True

            transports_handled = 0

            # D'abord, vérifier TOUJOURS les transports de prisonniers
            logger.debug("Vérification des transports de prisonniers...")
            prisoner_transport_data = await self._extract_prisoner_transport_links(mission)

            # Ensuite, chercher les transports sanitaires classiques
            try:
                transport_alert = await self.page.wait_for_selector(
                    'div.alert.alert-danger:not(.alert-missing-vehicles)',
                    timeout=3000, state='attached'
                )
            except Exception:
                transport_alert = None

            transport_data = []

            # Ajouter les transports de prisonniers s'il y en a
            if prisoner_transport_data:
                logger.debug(f"🚔 {len(prisoner_transport_data)} véhicule(s) avec transport de prisonniers détecté(s)")
                transport_data.extend(prisoner_transport_data)

            # Ajouter les transports sanitaires s'il y en a
            if transport_alert:
                alert_text = await transport_alert.inner_text()
                if "Transport nécessaire" in alert_text:
                    transport_links = await transport_alert.query_selector_all('a.btn.btn-xs.btn-success')
                    try:
                        for link in transport_links:
                            try:
                                href = await link.get_attribute('href')
                                text = await link.inner_text()
                                transport_data.append({'href': href, 'text': text, 'type': 'patient'})
                            except Exception as e:
                                logger.error(f"Erreur lors de l'extraction d'un lien de transport: {e}")
                                continue
                    finally:
                        for link in transport_links:
                            await link.dispose()

                    patient_count = len([t for t in transport_data if t.get('type') == 'patient'])
                    if patient_count > 0:
                        logger.debug(f"🚑 {patient_count} transport(s) sanitaire(s) détecté(s)")
                else:
                    logger.debug(f"Alerte détectée mais pas de transport sanitaire (contenu: '{alert_text.strip()[:50]}...')")
            else:
                logger.debug("Aucune alerte de transport sanitaire détectée")

            if not transport_data:
                logger.debug("Aucun transport (sanitaire ou prisonniers) disponible, poursuite du traitement de la mission")
                logger.info(f"✅ Aucun transport initial requis pour mission {mission.title} ({mission.id})")
                return True

            # Résumé des transports trouvés
            patient_transports = [t for t in transport_data if t.get('type') == 'patient']
            prisoner_transports = [t for t in transport_data if t.get('type') == 'prisoner']
            if patient_transports:
                logger.debug(f"🚑 {len(patient_transports)} transport(s) sanitaire(s) détecté(s)")
            if prisoner_transports:
                logger.debug(f"🚔 {len(prisoner_transports)} transport(s) de prisonniers détecté(s)")

            # Traiter chaque véhicule de transport via son URL
            for i, transport_info in enumerate(transport_data):
                try:
                    href = transport_info['href']
                    text = transport_info['text']
                    transport_type = transport_info.get('type', 'patient')
                    transport_emoji = "🚔" if transport_type == 'prisoner' else "🚑"
                    logger.debug(f"{transport_emoji} Transport initial {i+1}/{len(transport_data)}: {text}")

                    transport_url = f"https://www.operateur112.fr{href}" if href.startswith('/') else href
                    await self.page.goto(transport_url)
                    await self.page.wait_for_load_state('domcontentloaded', timeout=5000)

                    if transport_type == 'prisoner':
                        transport_success = await self._handle_prison_selection()
                    else:
                        transport_success = await self._handle_hospital_selection()

                    if transport_success:
                        transports_handled += 1
                        logger.info(f"✅ {transport_emoji} Transport initial {transports_handled} effectué pour {text}")

                        # Chercher le bouton "Passez au prochain véhicule"
                        next_vehicle_button = await self.page.query_selector('a.btn.btn-success[id^="next-vehicle-fms-"]')
                        if next_vehicle_button:
                            logger.debug("🔄 Passage au prochain véhicule")
                            await next_vehicle_button.click()
                            await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
                        else:
                            logger.debug("Aucun véhicule suivant pour ce transport")
                    else:
                        logger.warning(f"Échec du transport pour {text}")

                except Exception as e:
                    logger.error(f"Erreur lors du traitement du transport initial {i+1}: {e}")
                    continue

            if transports_handled > 0:
                logger.info(f"🚑 {transports_handled} transport(s) initial(aux) effectué(s) pour mission {mission.title} ({mission.id})")

                # S'assurer qu'on est bien sur la page de mission pour la suite
                mission_url = f"https://www.operateur112.fr/missions/{mission.id}"
                await self.page.goto(mission_url)
                await self.page.wait_for_load_state('domcontentloaded', timeout=5000)

                return True
            else:
                logger.debug(f"ℹ️ Aucun transport nécessaire pour mission {mission.title} ({mission.id})")
                return True

        except Exception as e:
            logger.error(f"Erreur lors des transports initiaux pour mission {mission.id}: {e}")
            return False

    async def _handle_hospital_selection(self) -> bool:
        """Sélectionne automatiquement le premier hôpital disponible."""
        try:
            hospitals_table = await self.page.wait_for_selector('#own-hospitals tbody', timeout=5000)
            if not hospitals_table:
                logger.warning("Tableau des hôpitaux non trouvé")
                return False

            hospital_button = await hospitals_table.query_selector('a.btn.btn-success')
            if not hospital_button:
                logger.warning("Aucun hôpital disponible pour le transport")
                return False

            hospital_text = await hospital_button.inner_text()
            logger.debug(f"🏥 Sélection hôpital: {hospital_text}")

            await hospital_button.click()
            await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
            return True

        except Exception as e:
            logger.error(f"Erreur lors de la sélection d'hôpital: {e}")
            return False

    async def _handle_prison_selection(self) -> bool:
        """Sélectionne automatiquement la première prison disponible."""
        try:
            await self.page.wait_for_load_state('domcontentloaded', timeout=5000)

            prison_button = await self.page.query_selector('a.btn.btn-success')
            if not prison_button:
                logger.warning("Aucune prison disponible pour le transport")
                return False

            prison_text = await prison_button.inner_text()
            logger.debug(f"🏢 Sélection prison: {prison_text}")

            await prison_button.click()
            await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
            return True

        except Exception as e:
            logger.error(f"Erreur lors de la sélection de prison: {e}")
            return False

    async def _extract_prisoner_transport_links(self, mission) -> list:
        """Extrait les liens de transport de prisonniers depuis le tableau des véhicules."""
        try:
            try:
                missing_vehicles_alert = await self.page.wait_for_selector(
                    'div.alert.alert-danger.alert-missing-vehicles',
                    timeout=3000, state='attached'
                )
            except Exception:
                missing_vehicles_alert = None

            if not missing_vehicles_alert:
                return []

            missing_text = await missing_vehicles_alert.inner_text()
            if "Des prisonniers doivent être transportés" not in missing_text:
                logger.debug("Alerte détectée mais ne concerne pas les transports de prisonniers")
                return []

            logger.debug("🚔 Transport de prisonniers requis détecté")

            prisoner_cells = await self.page.query_selector_all('td.vehicle_prisoner_select div[id^="prison-select-"]')
            if not prisoner_cells:
                logger.debug("Aucune cellule de sélection de prisonniers trouvée")
                return []

            transport_data = []
            try:
                for cell in prisoner_cells:
                    try:
                        success_link = await cell.query_selector('a.btn.btn-success')
                        if success_link:
                            href = await success_link.get_attribute('href')
                            text = await success_link.inner_text()

                            cell_id = await cell.get_attribute('id')
                            vehicle_id = cell_id.replace('prison-select-', '') if cell_id and cell_id.startswith('prison-select-') else 'unknown'

                            if href:
                                transport_data.append({
                                    'href': href,
                                    'text': f"🚔 Véhicule {vehicle_id} → {text}",
                                    'type': 'prisoner',
                                    'vehicle_id': vehicle_id
                                })
                                logger.debug(f"Lien de transport prisonnier trouvé: Véhicule {vehicle_id} → {text}")

                    except Exception as e:
                        logger.error(f"Erreur lors de l'extraction d'un lien de transport prisonnier: {e}")
                        continue
            finally:
                for cell in prisoner_cells:
                    await cell.dispose()

            return transport_data

        except Exception as e:
            logger.error(f"Erreur lors de l'extraction des liens de transport de prisonniers: {e}")
            return []

    async def extract_prisoner_count_from_mission_info(self) -> int:
        """Extrait le nombre de prisonniers depuis mission_general_info."""
        try:
            general_info = await self.page.query_selector('div#mission_general_info small')
            if not general_info:
                logger.debug("Div mission_general_info non trouvée")
                return 0

            content_html = await general_info.inner_html()

            prisoner_pattern = r'(\d+)\s*<img[^>]*prisoner_dark\.svg[^>]*>'
            matches = re.findall(prisoner_pattern, content_html)

            if matches:
                prisoner_count = sum(int(match) for match in matches)
                logger.debug(f"🚔 {prisoner_count} prisonnier(s) détecté(s) dans mission_general_info")
                return prisoner_count
            else:
                logger.debug("Aucun prisonnier détecté dans mission_general_info")
                return 0

        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du nombre de prisonniers: {e}")
            return 0
