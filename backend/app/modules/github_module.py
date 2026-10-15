"""Module GitHub : profil public d'un utilisateur GitHub à partir de son pseudo.

API publique, sans clé (limite ~60 req/h). Donne nom, bio, société, lieu,
site web, email public éventuel, compte Twitter/X, nb de dépôts et d'abonnés.
Bon pivot : les devs réutilisent souvent le même pseudo et déclarent des infos.
"""
from __future__ import annotations

import requests

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule


class GithubModule(OsintModule):
    name = "github"
    description = (
        "Récupère le profil public GitHub d'un pseudo : nom, bio, société, lieu, "
        "site web, email public, Twitter, nb de dépôts/abonnés. Gratuit."
    )
    accepts = [InputType.USERNAME]
    legal_notice = "Données publiques de l'API GitHub."

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.USERNAME.value:
            return ModuleResult(status="refused", detail="github n'accepte qu'un pseudo.")
        user = value.strip()
        try:
            resp = requests.get(f"https://api.github.com/users/{user}",
                               headers={"user-agent": "OJD-OSINT-App", "accept": "application/vnd.github+json"},
                               timeout=15)
        except requests.RequestException as exc:
            return ModuleResult(status="error", detail=f"Échec GitHub: {exc}")

        if resp.status_code == 404:
            return ModuleResult(status="ok", entities=[], detail=f"Aucun compte GitHub « {user} ».")
        if resp.status_code == 403:
            return ModuleResult(status="error", detail="Limite de débit GitHub atteinte (réessaie plus tard).")
        if resp.status_code != 200:
            return ModuleResult(status="error", detail=f"Réponse GitHub inattendue ({resp.status_code}).")

        d = resp.json()
        entities: list[ModuleResultEntity] = []
        meta = {"source": "github", "pseudo": user,
                "repos": d.get("public_repos"), "followers": d.get("followers"),
                "bio": d.get("bio"), "company": d.get("company"), "created": d.get("created_at")}
        entities.append(ModuleResultEntity(type="url", value=d.get("html_url") or f"https://github.com/{user}", extra=meta))
        if d.get("name"):
            entities.append(ModuleResultEntity(type="person", value=d["name"], extra=meta))
        if d.get("email"):
            entities.append(ModuleResultEntity(type="email", value=d["email"], extra={"source": "github"}))
        if d.get("location"):
            entities.append(ModuleResultEntity(type="location", value=d["location"], extra={"source": "github"}))
        if d.get("blog"):
            blog = d["blog"] if d["blog"].startswith("http") else "https://" + d["blog"]
            entities.append(ModuleResultEntity(type="url", value=blog, extra={"source": "github", "role": "site"}))
        if d.get("twitter_username"):
            entities.append(ModuleResultEntity(type="url", value=f"https://x.com/{d['twitter_username']}",
                                               extra={"source": "github", "reseau": "twitter"}))

        return ModuleResult(status="ok", entities=entities,
                            detail=f"Compte GitHub « {user} » : {d.get('public_repos', 0)} dépôts, "
                                   f"{d.get('followers', 0)} abonnés.")
