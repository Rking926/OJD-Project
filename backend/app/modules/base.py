"""Interface commune à tous les modules OSINT (plugins).

Pour ajouter un nouvel outil (ex: maigret, whois, holehe...), il suffit de
créer une classe héritant de `OsintModule` dans ce dossier et de l'ajouter
au registre dans `registry.py`. Le cœur de l'app (API, LLM, UI) n'a jamais
besoin d'être modifié.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class InputType(str, Enum):
    USERNAME = "username"
    EMAIL = "email"
    PHONE = "phone"
    DOMAIN = "domain"
    NAME = "name"
    IP = "ip"


@dataclass
class ModuleResultEntity:
    type: str
    value: str
    confidence: float = 1.0
    extra: dict = field(default_factory=dict)


@dataclass
class ModuleResult:
    status: str  # "ok" | "error" | "refused"
    entities: list[ModuleResultEntity] = field(default_factory=list)
    detail: str = ""
    raw: dict | None = None


class OsintModule(ABC):
    """Un module OSINT encapsule un outil (CLI, lib Python, ou appel HTTP)."""

    #: identifiant unique utilisé par le registre et le LLM (tool name)
    name: str = "base"
    #: description courte, utilisée par le LLM pour choisir le bon module
    description: str = ""
    #: types d'entrée acceptés (ex: [InputType.USERNAME])
    accepts: list[InputType] = []
    #: nécessite une config (clé API, session id...) avant usage
    requires_config: list[str] = []
    #: avertissement éventuel sur les CGU / cadre légal, affiché à l'utilisateur
    legal_notice: str = ""

    def is_configured(self, config: dict) -> bool:
        return all(config.get(key) for key in self.requires_config)

    @abstractmethod
    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        """Exécute la recherche et retourne un résultat normalisé."""
        raise NotImplementedError

    def manifest(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "accepts": [t.value for t in self.accepts],
            "requires_config": self.requires_config,
            "legal_notice": self.legal_notice,
        }
