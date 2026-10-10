"""Module WHOIS : informations publiques d'enregistrement d'un nom de domaine."""
from __future__ import annotations

import whois as whois_lib

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule


class WhoisModule(OsintModule):
    name = "whois"
    description = "Récupère les informations publiques WHOIS d'un nom de domaine (registrar, dates, DNS...)."
    accepts = [InputType.DOMAIN]
    legal_notice = "Données WHOIS publiques, fournies par les registres de noms de domaine."

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.DOMAIN.value:
            return ModuleResult(status="refused", detail="whois n'accepte que des domaines.")
        try:
            w = whois_lib.whois(value)
        except Exception as exc:  # noqa: BLE001
            return ModuleResult(status="error", detail=f"Échec whois: {exc}")

        if not w or not getattr(w, "domain_name", None):
            return ModuleResult(status="ok", entities=[], detail="Aucune donnée WHOIS trouvée.")

        entities = []
        for ns in (w.name_servers or []):
            if ns:
                entities.append(ModuleResultEntity(type="domain", value=str(ns).lower(), extra={"role": "nameserver"}))
        emails = w.emails
        if emails:
            emails = [emails] if isinstance(emails, str) else emails
            for e in emails:
                entities.append(ModuleResultEntity(type="email", value=e, extra={"role": "whois_contact"}))

        detail = {
            "registrar": w.registrar,
            "creation_date": str(w.creation_date),
            "expiration_date": str(w.expiration_date),
            "org": getattr(w, "org", None),
            "country": getattr(w, "country", None),
        }
        return ModuleResult(status="ok", entities=entities, detail="WHOIS récupéré.", raw=detail)
