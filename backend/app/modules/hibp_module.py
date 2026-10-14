"""Module HIBP (Have I Been Pwned) : vérifie si un email apparaît dans des
fuites de données connues.

Usage défensif typique : savoir si TON adresse (ou celle d'un périmètre que tu
es habilité à auditer) a été exposée dans une brèche, pour changer les mots de
passe concernés. On n'obtient jamais le mot de passe en clair — seulement la
liste des brèches et les catégories de données exposées.

L'API HIBP v3 nécessite une clé API payante (https://haveibeenpwned.com/API/Key).
Le module reste désactivé tant que `hibp_api_key` n'est pas fourni dans les
paramètres.
"""
from __future__ import annotations

import requests

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule

API_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{account}"


class HibpModule(OsintModule):
    name = "hibp"
    description = (
        "Vérifie si une adresse email apparaît dans des fuites de données connues "
        "(Have I Been Pwned). Retourne la liste des brèches et les catégories de "
        "données exposées. Ne révèle jamais de mot de passe en clair."
    )
    accepts = [InputType.EMAIL]
    requires_config = ["hibp_api_key"]
    legal_notice = (
        "Nécessite une clé API HIBP personnelle. À utiliser sur vos propres adresses "
        "ou sur un périmètre que vous êtes légalement habilité à auditer."
    )

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.EMAIL.value:
            return ModuleResult(status="refused", detail="hibp n'accepte qu'une adresse email.")

        api_key = config.get("hibp_api_key")
        if not api_key:
            return ModuleResult(
                status="refused",
                detail="Module désactivé : fournissez une 'hibp_api_key' dans les paramètres pour l'activer.",
            )

        headers = {
            "hibp-api-key": api_key,
            "user-agent": "OJD-OSINT-App",
        }
        try:
            resp = requests.get(
                API_URL.format(account=value),
                headers=headers,
                params={"truncateResponse": "false"},
                timeout=20,
            )
        except requests.RequestException as exc:  # réseau indisponible, etc.
            return ModuleResult(status="error", detail=f"Échec de la requête HIBP: {exc}")

        if resp.status_code == 404:
            return ModuleResult(status="ok", entities=[], detail="Aucune fuite connue pour cette adresse. 👍")
        if resp.status_code == 401:
            return ModuleResult(status="error", detail="Clé API HIBP invalide ou expirée.")
        if resp.status_code == 429:
            retry = resp.headers.get("retry-after", "?")
            return ModuleResult(status="error", detail=f"Limite de débit HIBP atteinte. Réessayez dans {retry}s.")
        if resp.status_code != 200:
            return ModuleResult(status="error", detail=f"Réponse HIBP inattendue ({resp.status_code}).")

        try:
            breaches = resp.json()
        except ValueError:
            return ModuleResult(status="error", detail="Réponse HIBP illisible.")

        entities: list[ModuleResultEntity] = []
        for b in breaches:
            name = b.get("Name") or b.get("Title") or "brèche inconnue"
            entities.append(ModuleResultEntity(
                type="breach",
                value=name,
                extra={
                    "title": b.get("Title"),
                    "breach_date": b.get("BreachDate"),
                    "data_classes": b.get("DataClasses"),
                    "verified": b.get("IsVerified"),
                },
            ))

        return ModuleResult(
            status="ok",
            entities=entities,
            detail=f"{len(entities)} fuite(s) trouvée(s) pour cette adresse.",
        )
