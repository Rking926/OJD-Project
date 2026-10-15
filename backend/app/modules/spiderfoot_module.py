"""Module SpiderFoot : méta-agrégateur OSINT (200+ modules) en mode headless.

Lance un scan PASSIF (sources ouvertes, pas de sondage actif) via le CLI
SpiderFoot et convertit les événements en entités. Décuple les sources d'un
coup (DNS, certificats, sous-domaines, emails, réseaux, threat intel…).

C'est un outil LOURD/LENT (un scan prend du temps) : il est donc exclu de
l'enquête rapide automatique et à lancer explicitement (« scan spiderfoot de X »).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule

DEFAULT_TIMEOUT = 180
# Jeu de modules rapides, sans clé API (infra : DNS, certificats, netblocks/ASN).
# Évite le scan « passif complet » qui lance 100+ modules et dépasse les délais.
_SF_MODULES = "sfp_dnsresolve,sfp_crt,sfp_sslcert,sfp_ripe,sfp_dnscommonsrv"

# Correspondance type d'événement SpiderFoot -> type d'entité OJD.
_TYPE_MAP = {
    "IP_ADDRESS": "ip", "IPV6_ADDRESS": "ip",
    "DOMAIN_NAME": "domain", "INTERNET_NAME": "domain", "CO_HOSTED_SITE": "domain",
    "AFFILIATE_DOMAIN_NAME": "domain", "AFFILIATE_INTERNET_NAME": "domain",
    "EMAILADDR": "email", "EMAILADDR_GENERIC": "email",
    "USERNAME": "username", "PHONE_NUMBER": "phone",
    "LINKED_URL_INTERNAL": "url", "LINKED_URL_EXTERNAL": "url",
    "SOCIAL_MEDIA": "url", "PHYSICAL_ADDRESS": "location", "GEOINFO": "location",
    "HUMAN_NAME": "person",
}


class SpiderFootModule(OsintModule):
    name = "spiderfoot"
    description = (
        "Méta-agrégateur OSINT SpiderFoot (200+ sources) : scan PASSIF d'une "
        "cible (domaine, email, IP, pseudo) renvoyant sous-domaines, IPs, emails, "
        "comptes, infos réseau… LENT : à lancer explicitement, pas pour une recherche rapide."
    )
    accepts = [InputType.DOMAIN, InputType.EMAIL, InputType.IP,
               InputType.USERNAME, InputType.PHONE]
    legal_notice = (
        "Scan passif en sources ouvertes. L'opérateur est responsable d'être "
        "autorisé à investiguer la cible."
    )

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        target = (value or "").strip()
        if not target:
            return ModuleResult(status="refused", detail="Cible manquante.")
        binary = shutil.which("spiderfoot") or shutil.which("sf.py")
        if not binary:
            return ModuleResult(status="error", detail="SpiderFoot non installé.")

        argv = [binary, "-s", target, "-m", _SF_MODULES, "-o", "json", "-q", "-S", "2000"]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT)
        except subprocess.TimeoutExpired:
            return ModuleResult(status="error", detail=f"SpiderFoot : délai dépassé ({DEFAULT_TIMEOUT}s). Cible trop large ?")
        except Exception as exc:  # noqa: BLE001
            return ModuleResult(status="error", detail=f"Échec SpiderFoot : {exc}")

        out = proc.stdout or ""
        rows = None
        try:
            rows = json.loads(out)
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", out, re.DOTALL)  # extrait le tableau JSON s'il y a du bruit
            if m:
                try:
                    rows = json.loads(m.group(0))
                except json.JSONDecodeError:
                    rows = None
        if not isinstance(rows, list):
            return ModuleResult(status="ok", entities=[], detail="SpiderFoot : aucun résultat exploitable.")

        seen: set[tuple[str, str]] = set()
        entities: list[ModuleResultEntity] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            # clés tolérantes selon la version (data/type ou majuscules)
            data = row.get("data") or row.get("Data") or row.get("value")
            etype = row.get("type") or row.get("Type") or row.get("event_type") or ""
            if not data:
                continue
            data = str(data).strip()
            mapped = _TYPE_MAP.get(str(etype).upper(), "other")
            key = (mapped, data)
            if key in seen or not data:
                continue
            seen.add(key)
            entities.append(ModuleResultEntity(
                type=mapped, value=data[:300],
                extra={"source": "spiderfoot", "sf_type": etype,
                       "module": row.get("module") or row.get("Source Module")},
            ))
            if len(entities) >= 500:
                break

        return ModuleResult(status="ok", entities=entities,
                            detail=f"SpiderFoot : {len(entities)} entité(s) agrégée(s) (scan passif).")
