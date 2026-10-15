"""Module Gravatar : à partir d'un email, récupère l'avatar et le profil public
Gravatar associé (souvent relié à WordPress et à des comptes déclarés).

Gratuit, sans clé API. Beaucoup de gens ont un Gravatar sans le savoir — c'est
un bon pivot (avatar + comptes liés déclarés publiquement).
"""
from __future__ import annotations

import hashlib

import requests

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule


class GravatarModule(OsintModule):
    name = "gravatar"
    description = (
        "À partir d'un email, récupère l'avatar Gravatar et le profil public "
        "associé (nom affiché, comptes déclarés, localisation). Gratuit."
    )
    accepts = [InputType.EMAIL]
    legal_notice = "Données publiques Gravatar."

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.EMAIL.value:
            return ModuleResult(status="refused", detail="gravatar n'accepte qu'un email.")
        email = value.strip().lower()
        h = hashlib.md5(email.encode()).hexdigest()
        headers = {"user-agent": "OJD-OSINT-App"}

        entities: list[ModuleResultEntity] = []
        # 1) l'avatar existe-t-il ?
        try:
            av = requests.get(f"https://www.gravatar.com/avatar/{h}", params={"d": "404", "s": "200"},
                              headers=headers, timeout=15)
            if av.status_code == 200:
                entities.append(ModuleResultEntity(
                    type="url", value=f"https://www.gravatar.com/avatar/{h}",
                    extra={"source": "gravatar", "role": "avatar", "email": email},
                ))
        except requests.RequestException as exc:
            return ModuleResult(status="error", detail=f"Échec Gravatar: {exc}")

        # 2) profil public (JSON)
        try:
            pr = requests.get(f"https://www.gravatar.com/{h}.json", headers=headers, timeout=15)
            if pr.status_code == 200:
                entry = (pr.json().get("entry") or [{}])[0]
                name = entry.get("displayName") or (entry.get("name") or {}).get("formatted")
                if name:
                    entities.append(ModuleResultEntity(type="person", value=name,
                                                       extra={"source": "gravatar", "email": email}))
                loc = entry.get("currentLocation")
                if loc:
                    entities.append(ModuleResultEntity(type="location", value=loc, extra={"source": "gravatar"}))
                for acc in (entry.get("accounts") or []):
                    url = acc.get("url")
                    if url:
                        entities.append(ModuleResultEntity(
                            type="url", value=url,
                            extra={"source": "gravatar", "reseau": acc.get("shortname") or acc.get("domain")},
                        ))
        except (requests.RequestException, ValueError):
            pass

        if not entities:
            return ModuleResult(status="ok", entities=[], detail="Aucun Gravatar public pour cet email.")
        return ModuleResult(status="ok", entities=entities,
                            detail=f"Gravatar trouvé : {len(entities)} élément(s).")
