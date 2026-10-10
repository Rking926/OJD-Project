"""Stockage local des paramètres (clé API LLM, config des modules).

Fichier JSON simple dans data/config.json — suffisant pour un usage local
mono-utilisateur. À remplacer par un stockage chiffré (keyring OS) avant
toute distribution commerciale.
"""
from __future__ import annotations

import json
import os

CONFIG_PATH = "./data/config.json"

DEFAULT_CONFIG = {
    "llm_provider": "anthropic",  # "anthropic" | "ollama"
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-4-5",
    "ollama_model": "llama3.1",
    "ollama_base_url": "http://localhost:11434",
    "module_config": {
        "instagram_sessionid": "",
    },
}


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    merged["module_config"] = {**DEFAULT_CONFIG["module_config"], **data.get("module_config", {})}
    return merged


def save_config(config: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def public_config(config: dict) -> dict:
    """Version renvoyée au frontend : masque les secrets."""
    out = dict(config)
    if out.get("anthropic_api_key"):
        out["anthropic_api_key"] = "••••" + out["anthropic_api_key"][-4:]
    mc = dict(out.get("module_config", {}))
    if mc.get("instagram_sessionid"):
        mc["instagram_sessionid"] = "••••configuré"
    out["module_config"] = mc
    return out
