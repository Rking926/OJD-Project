"""Exécution isolée des outils + garde-fou de périmètre (labo privé).

Objectif : permettre d'utiliser des outils actifs/offensifs **uniquement dans
un environnement maîtrisé** — un conteneur jetable (Docker) sur ton ordi, et
seulement contre des cibles que tu déclares (ton réseau de labo).

Deux fonctions :
  - `wrap_argv(argv, cfg)` : enrobe la commande selon le backend de sandbox
    configuré (docker / firejail / none).
  - `in_scope(target, cfg)` : vérifie qu'une cible appartient au périmètre
    autorisé avant de lancer un outil actif.

Le périmètre par défaut (si aucun n'est configuré) n'autorise que les
adresses privées (RFC1918), le loopback, et les hôtes .lab/.local/.test/
.localhost — c.-à-d. un labo local, jamais un tiers sur Internet.
"""
from __future__ import annotations

import ipaddress
import shutil
from urllib.parse import urlparse

_PRIVATE_SUFFIXES = (".lab", ".local", ".test", ".localhost")


def _extract_host(target: str) -> str:
    """Extrait l'hôte d'une cible (URL, host:port, IP ou domaine nu)."""
    t = target.strip()
    if "://" in t:
        t = urlparse(t).hostname or t
    # host:port éventuel (mais pas une IPv6 nue)
    if t.count(":") == 1:
        t = t.split(":", 1)[0]
    return t.strip("[]").lower()


def _matches_pattern(host: str, pattern: str) -> bool:
    pattern = pattern.strip().lower()
    if not pattern:
        return False
    # CIDR / réseau IP
    try:
        net = ipaddress.ip_network(pattern, strict=False)
        try:
            return ipaddress.ip_address(host) in net
        except ValueError:
            return False
    except ValueError:
        pass
    # suffixe d'hôte (.lab, exemple.interne…)
    if pattern.startswith("."):
        return host == pattern[1:] or host.endswith(pattern)
    return host == pattern


def _is_default_private(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return host == "localhost" or host.endswith(_PRIVATE_SUFFIXES)


def in_scope(target: str, cfg: dict) -> tuple[bool, str]:
    """Retourne (autorisé, raison). Appliqué aux outils actifs/offensifs."""
    sb = cfg.get("sandbox", {})
    if not sb.get("enforce_scope", True):
        return True, "périmètre non appliqué (enforce_scope=False)"

    host = _extract_host(target)
    if not host:
        return False, "cible vide"

    scope = [p for p in sb.get("scope", []) if p.strip()]
    if scope:
        for pat in scope:
            if _matches_pattern(host, pat):
                return True, f"dans le périmètre ({pat})"
        return False, (
            f"cible '{host}' hors du périmètre de labo autorisé. "
            f"Ajoute-la dans Paramètres → périmètre (sandbox.scope)."
        )

    if _is_default_private(host):
        return True, "périmètre par défaut (adresse privée / labo)"
    return False, (
        f"cible '{host}' publique : refusée par défaut. Les outils actifs ne "
        f"visent que le labo privé (adresses RFC1918, .lab/.local/.test) tant "
        f"qu'aucun périmètre explicite n'est configuré."
    )


def wrap_argv(argv: list[str], cfg: dict) -> list[str]:
    """Enrobe argv selon le backend de sandbox configuré."""
    sb = cfg.get("sandbox", {})
    backend = sb.get("backend", "none")

    if backend == "docker" and shutil.which("docker"):
        image = sb.get("image", "kalilinux/kali-rolling")
        network = sb.get("network", "")
        cmd = ["docker", "run", "--rm", "-i"]
        if network:
            cmd += ["--network", network]
        cmd += [image]
        return cmd + argv

    if backend == "firejail" and shutil.which("firejail"):
        return ["firejail", "--quiet", "--private", *argv]

    # "none" ou backend demandé mais binaire absent : exécution directe.
    return argv


def backend_status(cfg: dict) -> dict:
    sb = cfg.get("sandbox", {})
    backend = sb.get("backend", "none")
    available = backend == "none" or shutil.which(backend) is not None
    return {
        "backend": backend,
        "available": available,
        "isolated": backend in ("docker", "firejail") and available,
        "enforce_scope": sb.get("enforce_scope", True),
        "scope": sb.get("scope", []),
    }
