from typing import Optional, List
from loguru import logger

from ..config.settings import Settings
from ..utils.logger import setup_logger
from .browser_manager import BrowserManager
from .mission_manager import MissionManager
from ..models.mission import Mission


class OperateurBot:
    """Bot principal pour l'automatisation d'Opérateur 112"""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.from_env()

        # Configuration du logging
        setup_logger(self.settings)

        # Validation des paramètres
        if not self.settings.validate_credentials():
            raise ValueError("Username et password sont requis dans la configuration")

        # Composants principaux
        self.browser_manager = BrowserManager(self.settings)
        self.mission_manager: Optional[MissionManager] = None
        self.is_running = False

        logger.info("Bot Opérateur 112 v3 initialisé")

    async def start(self) -> None:
        """Démarre le bot et initialise tous les composants"""
        if self.is_running:
            logger.warning("Le bot est déjà en cours d'exécution")
            return

        logger.info("Démarrage du bot...")

        try:
            # Démarrer le navigateur
            await self.browser_manager.start()

            # Connexion au jeu
            login_success = await self._login()
            if not login_success:
                raise RuntimeError("Échec de la connexion")

            # Initialiser le gestionnaire de missions
            self.mission_manager = MissionManager(self.browser_manager, self.settings)

            # Charger les patterns d'apprentissage précédemment sauvegardés
            await self.mission_manager.initialize()

            self.is_running = True
            logger.info("Bot démarré avec succès!")

        except Exception as e:
            logger.error(f"Erreur lors du démarrage: {e}")
            await self.stop()
            raise

    async def stop(self) -> None:
        """Arrête proprement le bot"""
        if not self.is_running:
            return

        logger.info("Arrêt du bot...")

        try:
            # Arrêter le navigateur
            await self.browser_manager.stop()

            self.is_running = False
            logger.info("Bot arrêté")

        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt: {e}")

    async def _login(self) -> bool:
        """Connexion au jeu"""
        logger.info("Connexion en cours...")

        try:
            # Aller à la page de connexion
            await self.browser_manager.navigate_to(f"{self.settings.game_url}/users/sign_in")

            # Remplir le formulaire de connexion
            username_filled = await self.browser_manager.safe_fill("#user_email", self.settings.username)
            password_filled = await self.browser_manager.safe_fill("#user_password", self.settings.password)

            if not username_filled or not password_filled:
                logger.error("Impossible de remplir les champs de connexion")
                return False

            # Soumettre le formulaire
            submit_success = await self.browser_manager.safe_click("input[type='submit']")
            if not submit_success:
                logger.error("Impossible de cliquer sur le bouton de connexion")
                return False

            # Attendre la redirection (avec timeout pour éviter un blocage)
            try:
                await self.browser_manager.page.wait_for_load_state('domcontentloaded', timeout=10000)
            except Exception:
                pass

            # Vérifier la connexion
            page_title = await self.browser_manager.get_page_title()
            current_url = self.browser_manager.page.url

            if "sign_in" in current_url or "login" in current_url:
                logger.error("Connexion échouée - toujours sur la page de connexion")
                return False

            logger.info(f"Connexion réussie! Page actuelle: {page_title}")
            return True

        except Exception as e:
            logger.error(f"Erreur lors de la connexion: {e}")
            return False

    async def get_missions(self) -> List[Mission]:
        """Récupère toutes les missions disponibles"""
        self._ensure_running()
        return await self.mission_manager.get_all_missions()

    async def deploy_mission(self, mission_id: str, strategy: str = None) -> bool:
        """Déploie une mission spécifique"""
        self._ensure_running()

        # Trouver la mission
        missions = await self.get_missions()
        mission = next((m for m in missions if m.id == mission_id), None)

        if not mission:
            logger.error(f"Mission {mission_id} non trouvée")
            return False

        # Utiliser la version optimisée par défaut
        return await self.mission_manager.deploy_vehicles_for_mission_optimized(mission, strategy)

    async def run_auto_missions(self, max_missions: int = None) -> dict:
        """Lance le déploiement automatique de missions"""
        self._ensure_running()
        return await self.mission_manager.auto_deploy_missions(max_missions)

    async def run_continuous(self, cycles: int = -1, max_missions: int = None, cycle_delay: int = None) -> None:
        """Lance le bot en mode continu"""
        self._ensure_running()
        # Utiliser le délai configuré dans les settings si non spécifié
        if cycle_delay is None:
            cycle_delay = self.settings.cycle_delay
        await self.mission_manager.run_mission_cycle(cycles, max_missions, cycle_delay)

    async def refresh_session(self) -> bool:
        """Re-login sans redémarrer le navigateur (session expirée)"""
        logger.warning("Session expirée, tentative de reconnexion...")

        try:
            login_success = await self._login()
            if not login_success:
                logger.error("Reconnexion échouée")
                return False

            logger.info("Reconnexion réussie!")
            return True

        except Exception as e:
            logger.error(f"Erreur lors de la reconnexion: {e}")
            return False

    async def recover_browser(self) -> bool:
        """Tente de relancer le navigateur après un crash et se reconnecter"""
        logger.warning("Tentative de recovery du navigateur...")

        try:
            # Redémarrer le navigateur
            await self.browser_manager.restart()

            # Se reconnecter au jeu
            login_success = await self._login()
            if not login_success:
                logger.error("Recovery: échec de la reconnexion")
                return False

            # Réinitialiser le mission_manager avec le nouveau browser
            self.mission_manager = MissionManager(self.browser_manager, self.settings)
            await self.mission_manager.initialize()

            logger.info("Recovery du navigateur réussi!")
            return True

        except Exception as e:
            logger.error(f"Recovery du navigateur échoué: {e}")
            return False

    def _ensure_running(self) -> None:
        """Vérifie que le bot est en cours d'exécution"""
        if not self.is_running:
            raise RuntimeError("Le bot n'est pas démarré. Appelez start() d'abord.")
        if not self.mission_manager:
            raise RuntimeError("Le gestionnaire de missions n'est pas initialisé")

    async def get_status(self) -> dict:
        """Retourne le statut actuel du bot"""
        status = {
            "running": self.is_running,
            "browser_ready": self.browser_manager.is_ready(),
            "settings": {
                "game_url": self.settings.game_url,
                "username": self.settings.username,
                "strategy": self.settings.default_strategy,
                "auto_deploy": self.settings.auto_deploy
            }
        }

        return status

    async def take_screenshot(self, path: str = None) -> Optional[bytes]:
        """Prend une capture d'écran"""
        if not self.browser_manager.is_ready():
            logger.warning("Navigateur non prêt pour capture d'écran")
            return None

        return await self.browser_manager.take_screenshot(path)

    # Context manager support
    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
