"""Module DNS : enregistrements publics d'un domaine (A, AAAA, MX, NS, TXT).

Utilise `dnspython`. Donne les IPs (A/AAAA), les serveurs mail (MX), les
serveurs de noms (NS) et les enregistrements TXT (SPF, DKIM, vérifications…).
Import paresseux : si dnspython n'est pas installé, le module le signale
proprement sans casser le reste de l'app.
"""
from __future__ import annotations

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule

_RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT")


class DnsModule(OsintModule):
    name = "dns"
    description = (
        "Récupère les enregistrements DNS publics d'un domaine : IPs (A/AAAA), "
        "serveurs mail (MX), serveurs de noms (NS) et TXT (SPF/DKIM). Gratuit."
    )
    accepts = [InputType.DOMAIN]
    legal_notice = "Requêtes DNS publiques (données ouvertes)."

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.DOMAIN.value:
            return ModuleResult(status="refused", detail="dns n'accepte qu'un domaine.")
        try:
            import dns.resolver  # import paresseux
        except ImportError:
            return ModuleResult(status="error", detail="Lib 'dnspython' non installée (voir install.sh).")

        domain = value.strip().lower().lstrip("*.")
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 10.0
        resolver.timeout = 5.0

        entities: list[ModuleResultEntity] = []
        found: dict[str, list[str]] = {}
        for rtype in _RECORD_TYPES:
            try:
                answers = resolver.resolve(domain, rtype)
            except Exception:  # NXDOMAIN, NoAnswer, Timeout… -> on ignore ce type
                continue
            vals = []
            for r in answers:
                if rtype in ("A", "AAAA"):
                    ip = r.address
                    vals.append(ip)
                    entities.append(ModuleResultEntity(type="ip", value=ip, extra={"source": "dns", "record": rtype}))
                elif rtype == "MX":
                    host = str(r.exchange).rstrip(".").lower()
                    if host:  # ignore le "null MX" (".") = pas de serveur mail
                        vals.append(host)
                        entities.append(ModuleResultEntity(type="domain", value=host, extra={"source": "dns", "role": "mx"}))
                elif rtype == "NS":
                    host = str(r.target).rstrip(".").lower()
                    if host:
                        vals.append(host)
                        entities.append(ModuleResultEntity(type="domain", value=host, extra={"source": "dns", "role": "ns"}))
                elif rtype == "TXT":
                    txt = b"".join(r.strings).decode(errors="ignore") if hasattr(r, "strings") else str(r)
                    vals.append(txt)
            if vals:
                found[rtype] = vals

        # Les TXT (SPF/DKIM…) sont conservés comme une entité consultable.
        if found.get("TXT"):
            entities.append(ModuleResultEntity(
                type="other", value=f"TXT de {domain}",
                extra={"source": "dns", "txt": found["TXT"]},
            ))

        if not found:
            return ModuleResult(status="ok", entities=[], detail=f"Aucun enregistrement DNS résolu pour {domain}.")
        summary = ", ".join(f"{k}: {len(v)}" for k, v in found.items())
        return ModuleResult(status="ok", entities=entities, detail=f"DNS {domain} — {summary}.")
