"""Module générique construit à partir d'une définition d'outil utilisateur.

Permet d'exécuter n'importe quel outil ajouté depuis l'app, dans le sandbox
configuré, avec garde-fou de périmètre pour les outils actifs/offensifs.

La commande est toujours lancée en argv (jamais via un shell) → pas
d'injection de commande possible depuis la cible.
"""
from __future__ import annotations

import shlex
import subprocess

from ..config_store import load_config
from ..sandbox import in_scope, wrap_argv
from .base import ModuleResult, ModuleResultEntity, OsintModule


class UserCommandModule(OsintModule):
    def __init__(self, defn: dict):
        self._defn = defn
        self.name = defn["name"]
        self.active = defn.get("active", True)
        self._argv = defn["argv"]
        self._timeout = defn.get("timeout", 300)
        self._label = defn.get("input_label", "target")
        installed = defn.get("binary_installed", True)
        scope_note = " [outil actif : limité au périmètre de labo]" if self.active else ""
        missing = "" if installed else " ⚠ binaire non installé"
        self.description = (
            f"{defn.get('description', '')} (catégorie: {defn.get('category', 'autre')})"
            f"{scope_note}{missing}"
        )
        self.legal_notice = (
            "Outil ajouté par l'opérateur. Exécution dans le sandbox configuré ; "
            "l'opérateur est responsable d'être autorisé sur la cible."
        )

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": f"La cible ({self._label}) passée à l'outil.",
                },
            },
            "required": ["target"],
        }

    def run(self, target: str = "", config: dict | None = None,
            input_type: str = "", value: str = "", **_kw) -> ModuleResult:
        target = target or value or input_type
        if not target:
            return ModuleResult(status="refused", detail="Cible manquante.")

        cfg = load_config()

        if self.active:
            ok, reason = in_scope(target, cfg)
            if not ok:
                return ModuleResult(status="refused", detail=f"Refusé : {reason}")

        argv = [part.replace("{target}", target) for part in self._argv]
        full_argv = wrap_argv(argv, cfg)

        try:
            proc = subprocess.run(full_argv, capture_output=True, text=True, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            return ModuleResult(status="error", detail=f"{self.name} : délai dépassé ({self._timeout}s).")
        except FileNotFoundError:
            return ModuleResult(status="error", detail=f"{self.name} : binaire introuvable ({full_argv[0]}).")
        except Exception as exc:  # noqa: BLE001
            return ModuleResult(status="error", detail=f"Échec {self.name} : {exc}")

        output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
        entities = []
        if output:
            entities.append(ModuleResultEntity(
                type="other",
                value=f"{self.name} → {target}",
                extra={"command": shlex.join(argv), "output": output[:8000]},
            ))
        return ModuleResult(
            status="ok", entities=entities,
            detail=f"{self.name} exécuté (code {proc.returncode}, {len(output)} car. de sortie).",
            raw={"command": shlex.join(argv), "returncode": proc.returncode},
        )
