"""Lanceur générique d'outils de reconnaissance Kali installés.

Expose au LLM UN seul outil (`recon_tool`) capable de lancer n'importe quel
outil de reconnaissance/discovery installé sur la machine. Évite d'avoir à
déclarer 170 outils séparément.

Garde-fous :
  - seuls les outils `runnable` du catalogue (installés + catégorie
    Reconnaissance/Discovery) sont acceptés ;
  - timeout strict, sortie capturée et tronquée ;
  - chaque exécution est journalisée par l'orchestrateur (audit).

Pour les outils courants, un modèle de commande dédié est défini dans
ARG_TEMPLATES. Pour les autres, on tente `<cmd> <target>` par défaut, ce qui
ne marchera pas pour tous — l'outil reste alors consultable mais son
exécution auto peut échouer proprement.
"""
from __future__ import annotations

import shlex
import subprocess

from ..catalog_store import get_tool, runnable_tools
from .base import ModuleResult, ModuleResultEntity, OsintModule

# Modèles de commande pour les outils de reco les plus utiles.
# {target} est remplacé par la valeur fournie. Liste = argv (pas de shell).
ARG_TEMPLATES: dict[str, list[str]] = {
    "theHarvester": ["theHarvester", "-d", "{target}", "-b", "duckduckgo,bing,crtsh", "-l", "200"],
    "dnsrecon": ["dnsrecon", "-d", "{target}"],
    "dnsenum": ["dnsenum", "--noreverse", "{target}"],
    "dnsmap": ["dnsmap", "{target}"],
    "whatweb": ["whatweb", "--no-errors", "-a", "1", "{target}"],
    "sublist3r": ["sublist3r", "-d", "{target}"],
    "subfinder": ["subfinder", "-silent", "-d", "{target}"],
    "assetfinder": ["assetfinder", "--subs-only", "{target}"],
    "findomain": ["findomain", "-t", "{target}", "-q"],
    "amass": ["amass", "enum", "-passive", "-d", "{target}"],
    "dmitry": ["dmitry", "-winse", "{target}"],
    "photon": ["photon", "-u", "{target}", "-l", "1"],
}

DEFAULT_TIMEOUT = 120


class ReconToolModule(OsintModule):
    name = "recon_tool"
    description = (
        "Lance un outil Kali de reconnaissance installé (ex: theHarvester, dnsrecon, "
        "whatweb, amass, subfinder) sur une cible (domaine le plus souvent). "
        "Utilise 'tool' = le nom exact de l'outil, 'target' = la cible."
    )
    legal_notice = (
        "Reconnaissance en sources ouvertes uniquement. L'opérateur est responsable "
        "d'être autorisé à interroger la cible."
    )

    def input_schema(self) -> dict:
        runnable = [t["cmd"] for t in runnable_tools()]
        return {
            "type": "object",
            "properties": {
                "tool": {
                    "type": "string",
                    "description": "Nom exact de l'outil de reconnaissance à lancer.",
                    "enum": runnable or ["<aucun outil de reconnaissance installé>"],
                },
                "target": {
                    "type": "string",
                    "description": "La cible (domaine, hôte, IP...).",
                },
            },
            "required": ["tool", "target"],
        }

    # Signature compatible : l'orchestrateur appelle run(tool=..., target=...)
    def run(self, tool: str = "", target: str = "", config: dict | None = None,
            input_type: str = "", value: str = "") -> ModuleResult:
        tool = tool or input_type
        target = target or value
        if not tool or not target:
            return ModuleResult(status="refused", detail="Paramètres 'tool' et 'target' requis.")

        meta = get_tool(tool)
        if not meta:
            return ModuleResult(status="refused", detail=f"Outil inconnu du catalogue : {tool}")
        if not meta["runnable"]:
            reason = "non installé" if not meta["installed"] else "catégorie non autorisée à l'exécution auto"
            return ModuleResult(status="refused", detail=f"Outil '{tool}' {reason} ({meta['cat']}).")

        template = ARG_TEMPLATES.get(tool, [tool, "{target}"])
        argv = [part.replace("{target}", target) for part in template]

        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT)
        except subprocess.TimeoutExpired:
            return ModuleResult(status="error", detail=f"{tool} : délai dépassé ({DEFAULT_TIMEOUT}s).")
        except FileNotFoundError:
            return ModuleResult(status="error", detail=f"{tool} introuvable à l'exécution.")
        except Exception as exc:  # noqa: BLE001
            return ModuleResult(status="error", detail=f"Échec {tool} : {exc}")

        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        output = output.strip()

        # On stocke la sortie brute comme une entité consultable. Un parsing
        # fin par outil pourra être ajouté plus tard.
        entities = []
        if output:
            entities.append(ModuleResultEntity(
                type="other",
                value=f"{tool} → {target}",
                extra={"command": shlex.join(argv), "output": output[:8000]},
            ))

        detail = f"{tool} exécuté (code {proc.returncode}, {len(output)} caractères de sortie)."
        return ModuleResult(status="ok", entities=entities, detail=detail,
                            raw={"command": shlex.join(argv), "returncode": proc.returncode})
