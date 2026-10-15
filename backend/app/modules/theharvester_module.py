"""Module theHarvester : emails, sous-domaines et IPs d'un domaine, agrégés
depuis plusieurs moteurs de sources ouvertes (crt.sh, Bing, DuckDuckGo…).

Utilise le binaire `theHarvester` (présent sur Kali). On lui demande une
sortie JSON qu'on parse, avec repli sur la sortie texte si besoin. Sources
sans clé API par défaut pour rester opérationnel out-of-the-box.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule

_SOURCES = "duckduckgo,bing,crtsh,otx,rapiddns,certspotter"
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
DEFAULT_TIMEOUT = 240


def _bin() -> str | None:
    return shutil.which("theHarvester") or shutil.which("theharvester")


class TheHarvesterModule(OsintModule):
    name = "theharvester"
    description = (
        "Collecte emails, sous-domaines et IPs d'un domaine depuis plusieurs "
        "moteurs de sources ouvertes (crt.sh, Bing, DuckDuckGo, OTX…). "
        "Gratuit, sans clé API."
    )
    accepts = [InputType.DOMAIN]
    legal_notice = "Agrégation de sources ouvertes. L'opérateur reste responsable de l'usage."

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.DOMAIN.value:
            return ModuleResult(status="refused", detail="theharvester n'accepte qu'un domaine.")
        binary = _bin()
        if not binary:
            return ModuleResult(status="error", detail="theHarvester n'est pas installé (voir install.sh).")

        domain = value.strip().lower()
        with tempfile.TemporaryDirectory() as tmp:
            stem = str(Path(tmp) / "out")
            argv = [binary, "-d", domain, "-b", _SOURCES, "-l", "200", "-f", stem]
            try:
                proc = subprocess.run(argv, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT)
            except subprocess.TimeoutExpired:
                return ModuleResult(status="error", detail=f"theHarvester : délai dépassé ({DEFAULT_TIMEOUT}s).")
            except Exception as exc:  # noqa: BLE001
                return ModuleResult(status="error", detail=f"Échec theHarvester : {exc}")

            emails: set[str] = set()
            hosts: set[str] = set()
            ips: set[str] = set()

            jf = Path(stem + ".json")
            if jf.exists():
                try:
                    data = json.loads(jf.read_text(errors="ignore"))
                    emails.update(data.get("emails", []) or [])
                    for h in (data.get("hosts", []) or []):
                        host = str(h).split(":")[0].strip().lower()
                        if host:
                            hosts.add(host)
                    ips.update(str(i) for i in (data.get("ips", []) or []))
                except (json.JSONDecodeError, OSError):
                    pass

            # Repli : on récupère au moins les emails depuis la sortie texte.
            if not emails:
                emails.update(m.group(0) for m in _EMAIL_RE.finditer(proc.stdout or ""))

            entities: list[ModuleResultEntity] = []
            for e in sorted(emails):
                entities.append(ModuleResultEntity(type="email", value=e, extra={"source": "theharvester"}))
            for h in sorted(hosts):
                if h != domain:
                    entities.append(ModuleResultEntity(type="domain", value=h, extra={"source": "theharvester", "role": "subdomain"}))
            for ip in sorted(ips):
                entities.append(ModuleResultEntity(type="ip", value=ip, extra={"source": "theharvester"}))

            return ModuleResult(
                status="ok", entities=entities,
                detail=f"{len(emails)} email(s), {len(hosts)} hôte(s), {len(ips)} IP(s) via theHarvester.",
            )
