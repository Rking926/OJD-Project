"""Module Sherlock : recherche d'un pseudo sur des centaines de réseaux sociaux.

Utilise la librairie `sherlock-project` installée dans le venv. On appelle
son binaire en sous-processus pour rester isolé des détails internes de la
lib (qui change souvent de structure interne entre versions).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule


class SherlockModule(OsintModule):
    name = "sherlock"
    description = (
        "Recherche un nom d'utilisateur (pseudo) sur des centaines de réseaux "
        "sociaux et sites. Retourne les profils trouvés."
    )
    accepts = [InputType.USERNAME]
    legal_notice = (
        "Sherlock n'interroge que des pages publiques existantes (vérification "
        "d'URL). Usage encadré par les CGU de chaque site visité."
    )

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.USERNAME.value:
            return ModuleResult(status="refused", detail="sherlock n'accepte que des pseudos (username).")

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            try:
                proc = subprocess.run(
                    [
                        sys.executable, "-m", "sherlock_project",
                        value,
                        "--timeout", "15",
                        "--print-found",
                        "--no-color",
                        "--folderoutput", str(out_dir),
                        "--output", str(out_dir / f"{value}.txt"),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            except subprocess.TimeoutExpired:
                return ModuleResult(status="error", detail="sherlock a dépassé le délai imparti (180s).")
            except FileNotFoundError:
                return ModuleResult(status="error", detail="sherlock_project n'est pas installé dans l'environnement.")

            entities: list[ModuleResultEntity] = []
            result_file = out_dir / f"{value}.txt"
            if result_file.exists():
                for line in result_file.read_text(errors="ignore").splitlines():
                    line = line.strip()
                    if line.startswith("http"):
                        entities.append(ModuleResultEntity(type="url", value=line, extra={"username": value}))

            if not entities and proc.returncode not in (0, None):
                return ModuleResult(
                    status="error",
                    detail=f"sherlock a échoué (code {proc.returncode}): {proc.stderr[-500:]}",
                    raw={"stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]},
                )

            return ModuleResult(status="ok", entities=entities, detail=f"{len(entities)} profil(s) trouvé(s).")
