"""Registre central des modules OSINT disponibles.

Deux sources :
  1. les modules "cœur" codés en dur (sherlock, maigret, holehe, hibp,
     xposedornot, whois…) ;
  2. les outils ajoutés par l'utilisateur depuis l'app (user_tools.json),
     transformés à la volée en modules exécutables (`UserCommandModule`).

L'API, le LLM et l'UI découvrent le tout via `list_modules()` / `manifests()`.
Ajouter un outil = soit créer un fichier module ici, soit — bien plus simple —
le déclarer depuis l'app (menu Outils).
"""
from __future__ import annotations

from ..user_tools_store import load_tools
from .base import OsintModule
from .hibp_module import HibpModule
from .holehe_module import HoleheModule
from .kali_runner import ReconToolModule
from .maigret_module import MaigretModule
from .sherlock_module import SherlockModule
from .toutatis_module import ToutatisModule
from .user_command import UserCommandModule
from .whois_module import WhoisModule
from .xposedornot_module import XposedOrNotModule

_CORE: list[OsintModule] = [
    SherlockModule(),
    MaigretModule(),
    HoleheModule(),
    WhoisModule(),
    ToutatisModule(),
    XposedOrNotModule(),
    HibpModule(),
    ReconToolModule(),
]
_CORE_NAMES = {m.name for m in _CORE}


def _user_modules() -> list[OsintModule]:
    """Modules dérivés des outils utilisateur activés (rechargés à chaque appel
    pour refléter immédiatement les ajouts/suppressions depuis l'app)."""
    mods = []
    for defn in load_tools():
        if defn.get("enabled", True) and defn["name"] not in _CORE_NAMES:
            mods.append(UserCommandModule(defn))
    return mods


def list_modules() -> list[OsintModule]:
    return _CORE + _user_modules()


def get_module(name: str) -> OsintModule | None:
    for m in list_modules():
        if m.name == name:
            return m
    return None


def manifests() -> list[dict]:
    return [m.manifest() for m in list_modules()]
