"""Outils ajoutés par l'utilisateur depuis l'app (sans toucher au code).

Un outil = une définition JSON stockée dans data/user_tools.json :

    {
      "name": "nmap_scan",                 # identifiant unique (a-z0-9_)
      "description": "Scan de ports nmap",  # sert au LLM pour choisir l'outil
      "category": "scan",
      "argv": ["nmap", "-sV", "-T4", "{target}"],  # {target} = la cible
      "input_label": "target",
      "timeout": 300,
      "active": true,     # true = outil actif (périmètre de labo imposé)
      "enabled": true
    }

À l'enregistrement, le registre crée automatiquement un module exécutable
(`UserCommandModule`) exposé au LLM. Aucune modification de code nécessaire :
c'est le mécanisme « ajouter un outil ultra-facilement ».
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "user_tools.json"
_NAME_RE = re.compile(r"^[a-z0-9_]{2,40}$")


def load_tools() -> list[dict]:
    if not _STORE_PATH.exists():
        return []
    try:
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(tools: list[dict]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(tools, ensure_ascii=False, indent=2), encoding="utf-8")


def validate(defn: dict) -> dict:
    """Valide/normalise une définition. Lève ValueError si invalide."""
    name = str(defn.get("name", "")).strip().lower()
    if not _NAME_RE.match(name):
        raise ValueError("Nom invalide (a-z, 0-9, _, 2 à 40 caractères).")

    argv = defn.get("argv")
    if isinstance(argv, str):
        argv = argv.split()
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        raise ValueError("argv doit être une liste non vide de chaînes (ex: [\"nmap\", \"-sV\", \"{target}\"]).")
    if not any("{target}" in a for a in argv):
        raise ValueError("argv doit contenir le marqueur {target} là où va la cible.")

    binary = argv[0]
    try:
        timeout = int(defn.get("timeout", 300))
    except (TypeError, ValueError):
        raise ValueError("timeout doit être un entier (secondes).")
    timeout = max(5, min(timeout, 1800))

    return {
        "name": name,
        "description": str(defn.get("description", "")).strip() or f"Outil {name}",
        "category": str(defn.get("category", "autre")).strip() or "autre",
        "argv": argv,
        "input_label": str(defn.get("input_label", "target")).strip() or "target",
        "timeout": timeout,
        # active=True => outil actif, soumis au périmètre de labo (sandbox).
        # Mettre False pour un outil purement passif/OSINT (ex: lookup public).
        "active": bool(defn.get("active", True)),
        "enabled": bool(defn.get("enabled", True)),
        "binary_installed": shutil.which(binary) is not None,
    }


def add_tool(defn: dict) -> dict:
    tool = validate(defn)
    tools = load_tools()
    if any(t["name"] == tool["name"] for t in tools):
        raise ValueError(f"Un outil nommé '{tool['name']}' existe déjà.")
    tools.append(tool)
    _save(tools)
    return tool


def update_tool(name: str, defn: dict) -> dict:
    tools = load_tools()
    idx = next((i for i, t in enumerate(tools) if t["name"] == name), None)
    if idx is None:
        raise ValueError(f"Outil inconnu : {name}")
    merged = {**tools[idx], **defn, "name": name}
    tools[idx] = validate(merged)
    _save(tools)
    return tools[idx]


def delete_tool(name: str) -> bool:
    tools = load_tools()
    kept = [t for t in tools if t["name"] != name]
    if len(kept) == len(tools):
        return False
    _save(kept)
    return True
