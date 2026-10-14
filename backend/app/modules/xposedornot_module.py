"""Module XposedOrNot : vérifie si un email apparaît dans des fuites de données.

Alternative GRATUITE à HIBP : l'API publique de XposedOrNot
(https://xposedornot.com) ne demande aucune clé. Elle renvoie la liste des
brèches connues contenant l'adresse. On n'obtient jamais de mot de passe en
clair.

Usage défensif : savoir si TON adresse (ou un périmètre que tu es habilité à
auditer) a fuité, pour changer les mots de passe concernés.

Limites de débit de l'API : ~2 req/s, 25/h, 100/jour par IP.
"""
from __future__ import annotations

import requests

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule

API_URL = "https://api.xposedornot.com/v1/check-email/{account}"


class XposedOrNotModule(OsintModule):
    name = "xposedornot"
    description = (
        "Vérifie gratuitement si une adresse email apparaît dans des fuites de "
        "données connues (alternative à HIBP, sans clé API). Retourne la liste des "
        "brèches. Ne révèle jamais de mot de passe en clair."
    )
    accepts = [InputType.EMAIL]
    legal_notice = (
        "API publique gratuite. À utiliser sur vos propres adresses ou sur un "
        "périmètre que vous êtes légalement habilité à auditer."
    )

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.EMAIL.value:
            return ModuleResult(status="refused", detail="xposedornot n'accepte qu'une adresse email.")

        try:
            resp = requests.get(
                API_URL.format(account=value),
                headers={"user-agent": "OJD-OSINT-App"},
                timeout=20,
            )
        except requests.RequestException as exc:
            return ModuleResult(status="error", detail=f"Échec de la requête XposedOrNot: {exc}")

        if resp.status_code == 429:
            retry = resp.headers.get("retry-after", "?")
            return ModuleResult(status="error", detail=f"Limite de débit XposedOrNot atteinte. Réessayez dans {retry}s.")

        try:
            data = resp.json()
        except ValueError:
            return ModuleResult(status="error", detail=f"Réponse XposedOrNot illisible ({resp.status_code}).")

        # Aucune fuite : l'API renvoie {"Error": "Not found", ...}
        if isinstance(data, dict) and data.get("Error"):
            return ModuleResult(status="ok", entities=[], detail="Aucune fuite connue pour cette adresse. 👍")

        # Fuites trouvées : {"breaches": [["Nom1", "Nom2", ...]], ...}
        raw_breaches = data.get("breaches") if isinstance(data, dict) else None
        names: list[str] = []
        if isinstance(raw_breaches, list):
            for item in raw_breaches:
                if isinstance(item, list):
                    names.extend(str(n) for n in item)
                elif item:
                    names.append(str(item))

        if not names:
            return ModuleResult(status="ok", entities=[], detail="Aucune fuite connue pour cette adresse. 👍")

        entities = [
            ModuleResultEntity(type="breach", value=name, extra={"source": "xposedornot"})
            for name in names
        ]
        return ModuleResult(
            status="ok",
            entities=entities,
            detail=f"{len(entities)} fuite(s) trouvée(s) pour cette adresse.",
        )
