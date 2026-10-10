"""Catalogue des outils Kali (kali.org/tools).

Charge catalog.json (468 outils) et indique lesquels sont réellement
installés sur la machine. Sert à :
  - afficher le catalogue complet, cherchable, dans l'UI ;
  - savoir quels outils de reconnaissance l'IA a le droit de lancer.

Seules les catégories listées dans RECON_CATEGORIES peuvent être exécutées
automatiquement par l'orchestrateur. Les outils offensifs (C2, exploitation,
vol d'identifiants, impact/DoS...) restent consultables mais ne sont jamais
lancés par l'IA.
"""
from __future__ import annotations

import functools
import json
import shutil
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "catalog.json"

# Catégories autorisées à l'exécution automatique (OSINT / sources ouvertes).
RECON_CATEGORIES = {"Reconnaissance", "Discovery"}


@functools.lru_cache(maxsize=1)
def _raw_catalog() -> list[dict]:
    if not _CATALOG_PATH.exists():
        return []
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def catalog(refresh: bool = False) -> list[dict]:
    """Retourne le catalogue enrichi d'un champ `installed` et `runnable`."""
    if refresh:
        _installed.cache_clear()
    out = []
    for t in _raw_catalog():
        cmd = t.get("cmd", "")
        installed = _installed(cmd)
        out.append({
            "cat": t.get("cat", ""),
            "sub": t.get("sub", ""),
            "pkg": t.get("pkg", ""),
            "cmd": cmd,
            "desc": t.get("desc", ""),
            "installed": installed,
            # exécutable par l'IA seulement si installé ET catégorie recon/discovery
            "runnable": installed and t.get("cat", "") in RECON_CATEGORIES,
        })
    return out


@functools.lru_cache(maxsize=4096)
def _installed(cmd: str) -> bool:
    return bool(cmd) and shutil.which(cmd) is not None


def runnable_tools() -> list[dict]:
    """Outils de reconnaissance installés, autorisés à l'exécution auto."""
    return [t for t in catalog() if t["runnable"]]


def get_tool(cmd: str) -> dict | None:
    for t in catalog():
        if t["cmd"] == cmd:
            return t
    return None


def stats() -> dict:
    cat = catalog()
    return {
        "total": len(cat),
        "installed": sum(1 for t in cat if t["installed"]),
        "runnable": sum(1 for t in cat if t["runnable"]),
    }
