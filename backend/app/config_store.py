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
    "llm_provider": "ollama",  # "anthropic" | "ollama" — défaut : IA locale gratuite
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-4-5",
    "ollama_model": "huihui_ai/qwen2.5-abliterate:7b",
    "ollama_base_url": "http://localhost:11434",
    "module_config": {
        "instagram_sessionid": "",
        "hibp_api_key": "",
    },
    # Exécution des outils actifs/offensifs : sandbox + périmètre de cibles.
    "sandbox": {
        # "none"   : exécution directe sur l'hôte (déconseillé pour l'offensif)
        # "docker" : chaque outil tourne dans un conteneur jetable (recommandé)
        # "firejail": isolation légère via firejail
        "backend": "none",
        "image": "kalilinux/kali-rolling",
        "network": "ojd-lab",  # réseau Docker isolé pour le labo
        # Si True, un outil actif ne peut viser qu'une cible du périmètre (labo).
        "enforce_scope": True,
        # Cibles autorisées : CIDR, IP, ou suffixe d'hôte (ex: ".lab", ".local").
        # Vide => périmètre par défaut : adresses privées (RFC1918) + loopback
        # + hôtes .lab/.local/.test/.localhost.
        "scope": [],
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
    merged["sandbox"] = {**DEFAULT_CONFIG["sandbox"], **data.get("sandbox", {})}
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
    if mc.get("hibp_api_key"):
        mc["hibp_api_key"] = "••••configuré"
    out["module_config"] = mc
    return out
