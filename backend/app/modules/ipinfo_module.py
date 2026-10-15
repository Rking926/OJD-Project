"""Module IP : géolocalisation et infos réseau d'une adresse IP.

Sans clé API : utilise l'API publique gratuite ip-api.com. Donne pays, ville,
opérateur/ISP, organisation, système autonome (AS) et DNS inverse.

Limite de débit ip-api : ~45 requêtes/minute par IP source.
"""
from __future__ import annotations

import requests

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule

_FIELDS = "status,message,country,regionName,city,isp,org,as,reverse,lat,lon,query"


class IpInfoModule(OsintModule):
    name = "ipinfo"
    description = (
        "Géolocalise une adresse IP et donne son opérateur/ISP, organisation, "
        "système autonome (AS) et DNS inverse. Gratuit, sans clé API."
    )
    accepts = [InputType.IP]
    legal_notice = "Données publiques de géolocalisation IP (ip-api.com)."

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.IP.value:
            return ModuleResult(status="refused", detail="ipinfo n'accepte qu'une adresse IP.")
        ip = value.strip()
        try:
            resp = requests.get(
                f"http://ip-api.com/json/{ip}", params={"fields": _FIELDS, "lang": "fr"},
                headers={"user-agent": "OJD-OSINT-App"}, timeout=15,
            )
        except requests.RequestException as exc:
            return ModuleResult(status="error", detail=f"Échec ip-api: {exc}")

        try:
            d = resp.json()
        except ValueError:
            return ModuleResult(status="error", detail=f"Réponse ip-api illisible ({resp.status_code}).")
        if d.get("status") != "success":
            return ModuleResult(status="error", detail=f"ip-api: {d.get('message', 'échec')}.")

        city = d.get("city"); region = d.get("regionName"); country = d.get("country")
        isp = d.get("isp"); org = d.get("org"); asn = d.get("as"); rev = d.get("reverse")
        lieu = ", ".join(x for x in (city, region, country) if x)
        extra = {"isp": isp, "org": org, "as": asn, "reverse": rev,
                 "lat": d.get("lat"), "lon": d.get("lon"), "source": "ip-api"}

        entities: list[ModuleResultEntity] = []
        if lieu:
            entities.append(ModuleResultEntity(type="location", value=lieu, extra=extra))
        if isp:
            entities.append(ModuleResultEntity(type="other", value=f"ISP: {isp}", extra=extra))
        if asn:
            entities.append(ModuleResultEntity(type="other", value=f"AS: {asn}", extra=extra))
        if rev:
            entities.append(ModuleResultEntity(type="domain", value=rev, extra={"role": "reverse_dns", "ip": ip}))

        return ModuleResult(status="ok", entities=entities,
                            detail=f"{ip} — {lieu or 'localisation inconnue'}"
                                   + (f", {isp}" if isp else "") + ".")
