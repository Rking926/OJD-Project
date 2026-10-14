"""Module holehe : à partir d'un email, liste les sites où un compte existe.

holehe teste l'email contre les fonctions "mot de passe oublié" / "inscription"
de ~120 sites pour détecter où il est utilisé, sans alerter la cible. Gratuit,
sans clé API.

Usage défensif : cartographier les comptes liés à TON adresse pour faire le
ménage, ou un périmètre que tu es habilité à auditer.
"""
from __future__ import annotations

import os
import subprocess
import sys

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule

HOLEHE_BIN = os.path.join(os.path.dirname(sys.executable), "holehe")


class HoleheModule(OsintModule):
    name = "holehe"
    description = (
        "À partir d'une adresse email, liste les sites où un compte existe "
        "(Twitter, Instagram, Spotify, etc.). Gratuit, sans clé API. Ne révèle "
        "aucun mot de passe."
    )
    accepts = [InputType.EMAIL]
    legal_notice = (
        "N'alerte pas la cible. À utiliser sur vos propres adresses ou un périmètre "
        "que vous êtes légalement habilité à auditer."
    )

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.EMAIL.value:
            return ModuleResult(status="refused", detail="holehe n'accepte qu'une adresse email.")

        try:
            proc = subprocess.run(
                [HOLEHE_BIN, "--only-used", "--no-color", value],
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            return ModuleResult(status="error", detail="holehe a dépassé le délai imparti (180s).")
        except FileNotFoundError:
            return ModuleResult(status="error", detail="holehe n'est pas installé dans l'environnement.")

        entities: list[ModuleResultEntity] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            # holehe marque les sites utilisés par un '[+] nom_du_site'
            if line.startswith("[+]"):
                site = line[3:].strip()
                if site:
                    entities.append(ModuleResultEntity(
                        type="account",
                        value=site,
                        extra={"email": value, "source": "holehe"},
                    ))

        if not entities and proc.returncode not in (0, None):
            return ModuleResult(
                status="error",
                detail=f"holehe a échoué (code {proc.returncode}): {proc.stderr[-300:]}",
            )

        return ModuleResult(
            status="ok",
            entities=entities,
            detail=f"{len(entities)} compte(s) lié(s) à cette adresse.",
        )
