"""Module Maigret : recherche d'un pseudo sur 2500+ sites.

Équivalent de Sherlock mais nettement plus large et capable d'extraire des
infos des profils trouvés. Gratuit, sans clé API. On parse la sortie texte
pour rester robuste aux changements de format de rapport.

Usage encadré par les CGU de chaque site visité (vérification de pages
publiques). À utiliser sur vos propres identifiants ou un périmètre autorisé.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule

MAIGRET_BIN = os.path.join(os.path.dirname(sys.executable), "maigret")
_URL_RE = re.compile(r"https?://\S+")


class MaigretModule(OsintModule):
    name = "maigret"
    description = (
        "Recherche un nom d'utilisateur (pseudo) sur plus de 2500 sites et réseaux "
        "sociaux. Version plus complète que Sherlock. Retourne les profils trouvés. "
        "Gratuit, sans clé API."
    )
    accepts = [InputType.USERNAME]
    legal_notice = (
        "Vérifie des pages publiques existantes. Usage encadré par les CGU de chaque "
        "site. À utiliser sur vos propres identifiants ou un périmètre autorisé."
    )

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.USERNAME.value:
            return ModuleResult(status="refused", detail="maigret n'accepte qu'un pseudo (username).")

        try:
            proc = subprocess.run(
                [
                    MAIGRET_BIN, value,
                    "--no-color",
                    "--no-progressbar",
                    "--no-autoupdate",
                    "--timeout", "15",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return ModuleResult(status="error", detail="maigret a dépassé le délai imparti (300s).")
        except FileNotFoundError:
            return ModuleResult(status="error", detail="maigret n'est pas installé dans l'environnement.")

        entities: list[ModuleResultEntity] = []
        seen: set[str] = set()
        for line in proc.stdout.splitlines():
            line = line.strip()
            # maigret marque les profils trouvés par un '[+]' suivi d'une URL
            if line.startswith("[+]"):
                m = _URL_RE.search(line)
                if m:
                    url = m.group(0).rstrip(".,);")
                    if url not in seen:
                        seen.add(url)
                        entities.append(ModuleResultEntity(
                            type="url", value=url, extra={"username": value, "source": "maigret"},
                        ))

        if not entities and proc.returncode not in (0, None):
            return ModuleResult(
                status="error",
                detail=f"maigret a échoué (code {proc.returncode}): {proc.stderr[-300:]}",
            )

        return ModuleResult(
            status="ok",
            entities=entities,
            detail=f"{len(entities)} profil(s) trouvé(s).",
        )
