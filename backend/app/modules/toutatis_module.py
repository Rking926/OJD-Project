"""Module Toutatis : infos Instagram à partir d'un sessionid.

⚠️ Toutatis utilise un `sessionid` de compte Instagram pour interroger l'API
privée d'Instagram. Cela sort du cadre des CGU d'Instagram et peut exposer
le compte utilisé à une suspension. Ce module est donc désactivé par défaut
(`requires_config`) : il ne s'exécute que si l'utilisateur fournit lui-même
un sessionid dans les paramètres, en connaissance de cause.

Le code appelle la lib `toutatis` si elle est installée ; sinon il retourne
une erreur explicite plutôt que de planter silencieusement.
"""
from __future__ import annotations

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule


class ToutatisModule(OsintModule):
    name = "toutatis"
    description = (
        "Récupère des informations publiques d'un profil Instagram (id, bio, "
        "téléphone/email partiellement masqués si exposés par l'API) à partir "
        "d'un nom d'utilisateur. Nécessite un sessionid Instagram fourni par l'utilisateur."
    )
    accepts = [InputType.USERNAME]
    requires_config = ["instagram_sessionid"]
    legal_notice = (
        "⚠️ Utilise l'API privée d'Instagram via un sessionid personnel : hors cadre "
        "officiel des CGU Instagram. À n'utiliser que dans un contexte légalement "
        "autorisé (enquête habilitée, consentement) et à vos propres risques pour "
        "le compte utilisé."
    )

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.USERNAME.value:
            return ModuleResult(status="refused", detail="toutatis n'accepte que des pseudos Instagram.")

        session_id = config.get("instagram_sessionid")
        if not session_id:
            return ModuleResult(
                status="refused",
                detail="Module désactivé : fournissez un 'instagram_sessionid' dans les paramètres pour l'activer.",
            )

        try:
            from toutatis.exceptions import UserNotFound
            from toutatis.toutatis import Toutatis
        except ImportError:
            return ModuleResult(
                status="error",
                detail="La librairie 'toutatis' n'est pas installée. Installez-la avec: pip install toutatis",
            )

        try:
            client = Toutatis(sessionid=session_id)
            info = client.username(value)
        except UserNotFound:
            return ModuleResult(status="ok", entities=[], detail="Profil Instagram introuvable.")
        except Exception as exc:  # noqa: BLE001
            return ModuleResult(status="error", detail=f"Échec toutatis: {exc}")

        entities = []
        data = getattr(info, "__dict__", {}) or {}
        if data.get("obfuscated_email"):
            entities.append(ModuleResultEntity(type="email", value=data["obfuscated_email"], confidence=0.5, extra={"masked": True}))
        if data.get("obfuscated_phone"):
            entities.append(ModuleResultEntity(type="phone", value=data["obfuscated_phone"], confidence=0.5, extra={"masked": True}))

        return ModuleResult(status="ok", entities=entities, detail="Profil Instagram récupéré.", raw=data)
