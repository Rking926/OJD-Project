"""Registre central des modules OSINT disponibles.

Ajouter un outil = créer un fichier module + l'instancier ici. Rien d'autre
à modifier : l'API, le LLM et l'UI le découvrent automatiquement via
`list_modules()` / `manifest()`.
"""
from __future__ import annotations

from .base import OsintModule
from .sherlock_module import SherlockModule
from .toutatis_module import ToutatisModule
from .whois_module import WhoisModule

_MODULES: dict[str, OsintModule] = {
    m.name: m
    for m in [
        SherlockModule(),
        WhoisModule(),
        ToutatisModule(),
    ]
}


def list_modules() -> list[OsintModule]:
    return list(_MODULES.values())


def get_module(name: str) -> OsintModule | None:
    return _MODULES.get(name)


def manifests() -> list[dict]:
    return [m.manifest() for m in _MODULES.values()]
