"""Registre central des modules OSINT disponibles.

Ajouter un outil = créer un fichier module + l'instancier ici. Rien d'autre
à modifier : l'API, le LLM et l'UI le découvrent automatiquement via
`list_modules()` / `manifest()`.
"""
from __future__ import annotations

from .base import OsintModule
from .hibp_module import HibpModule
from .holehe_module import HoleheModule
from .kali_runner import ReconToolModule
from .maigret_module import MaigretModule
from .sherlock_module import SherlockModule
from .toutatis_module import ToutatisModule
from .whois_module import WhoisModule
from .xposedornot_module import XposedOrNotModule

_MODULES: dict[str, OsintModule] = {
    m.name: m
    for m in [
        SherlockModule(),
        MaigretModule(),
        WhoisModule(),
        ToutatisModule(),
        XposedOrNotModule(),
        HoleheModule(),
        HibpModule(),
        ReconToolModule(),
    ]
}


def list_modules() -> list[OsintModule]:
    return list(_MODULES.values())


def get_module(name: str) -> OsintModule | None:
    return _MODULES.get(name)


def manifests() -> list[dict]:
    return [m.manifest() for m in _MODULES.values()]
