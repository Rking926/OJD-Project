"""Module crt.sh : sous-domaines via les logs de transparence des certificats.

Sans clé API, sans installation : interroge simplement l'API publique
https://crt.sh. Très efficace pour cartographier les sous-domaines d'un
domaine (souvent plus complet qu'un bruteforce DNS).
"""
from __future__ import annotations

import requests

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule


class CrtShModule(OsintModule):
    name = "crtsh"
    description = (
        "Liste les sous-domaines d'un domaine via les certificats TLS publics "
        "(Certificate Transparency, crt.sh). Gratuit, sans clé API."
    )
    accepts = [InputType.DOMAIN]
    legal_notice = "Données publiques de transparence des certificats (crt.sh)."

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.DOMAIN.value:
            return ModuleResult(status="refused", detail="crtsh n'accepte qu'un domaine.")
        domain = value.strip().lstrip("*.").lower()
        try:
            resp = requests.get(
                "https://crt.sh/", params={"q": domain, "output": "json"},
                headers={"user-agent": "OJD-OSINT-App"}, timeout=30,
            )
        except requests.RequestException as exc:
            return ModuleResult(status="error", detail=f"Échec crt.sh: {exc}")
        if resp.status_code != 200:
            return ModuleResult(status="error", detail=f"Réponse crt.sh inattendue ({resp.status_code}).")
        try:
            rows = resp.json()
        except ValueError:
            return ModuleResult(status="ok", entities=[], detail="Aucun certificat / réponse vide.")

        subs: set[str] = set()
        for row in rows:
            for field in ("name_value", "common_name"):
                val = row.get(field) or ""
                for name in str(val).splitlines():
                    name = name.strip().lstrip("*.").lower()
                    if name and name.endswith(domain) and " " not in name:
                        subs.add(name)
        subs.discard(domain)

        entities = [
            ModuleResultEntity(type="domain", value=s, extra={"source": "crtsh", "role": "subdomain"})
            for s in sorted(subs)
        ]
        return ModuleResult(status="ok", entities=entities,
                            detail=f"{len(entities)} sous-domaine(s) trouvé(s) via crt.sh.")
