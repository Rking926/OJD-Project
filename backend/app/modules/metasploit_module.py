"""Module Metasploit : lance un module MSF (auxiliary / exploit) contre une
cible de LABO, de façon non interactive, à périmètre strict.

But pédagogique : apprendre le cycle scan → exploit → vérification sur TES
propres machines de test (typiquement une VM volontairement vulnérable, ex.
Metasploitable2 dans QEMU, exposée en loopback via port-forward).

Garde-fous :
  - périmètre STRICT (`in_scope_strict`) : uniquement 127.0.0.1 (ta VM) ou une
    cible que tu as déclarée explicitement — jamais le reste du réseau ;
  - tous les paramètres (module, options, payload) sont validés par regex ;
  - exécution en argv + commandes MSF assainies (pas d'injection depuis la cible) ;
  - timeout strict, sortie capturée et tronquée ;
  - exécution non interactive (`run; exit`) : idéal pour les scanners, la
    détection de version et le `check` d'exploit. Les sessions Meterpreter
    interactives (post-exploitation type caméra/micro) se pilotent dans
    msfconsole ; un gestionnaire de sessions pourra être ajouté plus tard.
"""
from __future__ import annotations

import re
import shutil
import subprocess

from ..config_store import load_config
from ..sandbox import in_scope_strict
from .base import ModuleResult, ModuleResultEntity, OsintModule

_MODULE_RE = re.compile(r"^(auxiliary|exploit|post|scanner)/[a-z0-9][a-z0-9_/\-]*$")
_PAYLOAD_RE = re.compile(r"^[a-z0-9][a-z0-9_/\-]*$")
_OPTKEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_HOST_RE = re.compile(r"^[A-Za-z0-9_.\-:]+$")

DEFAULT_TIMEOUT = 300


def _clean_value(v) -> str | None:
    """Valeur d'option sûre : pas de retour ligne ni de ';' (anti-injection MSF)."""
    s = str(v)
    if "\n" in s or "\r" in s or ";" in s:
        return None
    return s


class MetasploitModule(OsintModule):
    name = "metasploit"
    description = (
        "Lance un module Metasploit (auxiliary/exploit/post) contre une cible de "
        "LABO et retourne la sortie. Paramètres : 'module' (ex: "
        "auxiliary/scanner/portscan/tcp ou exploit/unix/ftp/vsftpd_234_backdoor), "
        "'target' (RHOSTS), 'rport' optionnel, 'options' (dict) optionnel, "
        "'payload'/'lhost'/'lport' optionnels. Non interactif."
    )
    legal_notice = (
        "Outil d'exploitation à usage LABO uniquement. Cible limitée au loopback "
        "(VM locale) ou à une cible explicitement déclarée. L'opérateur est "
        "responsable de ne viser que des systèmes qu'il possède."
    )

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "module": {"type": "string", "description": "Chemin du module MSF (ex: auxiliary/scanner/ssh/ssh_version)."},
                "target": {"type": "string", "description": "RHOSTS — cible de labo (127.0.0.1 ou cible déclarée)."},
                "rport": {"type": "integer", "description": "RPORT optionnel."},
                "options": {"type": "object", "description": "Options MSF supplémentaires {CLE: valeur}."},
                "payload": {"type": "string", "description": "PAYLOAD optionnel (pour un exploit)."},
                "lhost": {"type": "string", "description": "LHOST optionnel."},
                "lport": {"type": "integer", "description": "LPORT optionnel."},
            },
            "required": ["module", "target"],
        }

    def run(self, module: str = "", target: str = "", rport=None, options=None,
            payload: str = "", lhost: str = "", lport=None,
            config: dict | None = None, input_type: str = "", value: str = "",
            **_kw) -> ModuleResult:
        module = (module or input_type).strip()
        target = (target or value).strip()
        if not module or not target:
            return ModuleResult(status="refused", detail="Paramètres 'module' et 'target' requis.")

        if not _MODULE_RE.match(module):
            return ModuleResult(status="refused", detail=f"Nom de module MSF invalide : {module}")
        if not _HOST_RE.match(target):
            return ModuleResult(status="refused", detail=f"Cible invalide : {target}")

        cfg = load_config()
        ok, reason = in_scope_strict(target, cfg)
        if not ok:
            return ModuleResult(status="refused", detail=f"Refusé : {reason}")

        if not shutil.which("msfconsole"):
            return ModuleResult(status="error", detail="msfconsole introuvable (Metasploit non installé).")

        cmds = [f"use {module}", f"set RHOSTS {target}"]

        if rport is not None:
            try:
                p = int(rport)
                if not (1 <= p <= 65535):
                    raise ValueError
            except (TypeError, ValueError):
                return ModuleResult(status="refused", detail="rport invalide.")
            cmds.append(f"set RPORT {p}")

        for k, v in (options or {}).items():
            if not _OPTKEY_RE.match(str(k)):
                return ModuleResult(status="refused", detail=f"Clé d'option invalide : {k}")
            cv = _clean_value(v)
            if cv is None:
                return ModuleResult(status="refused", detail=f"Valeur d'option non autorisée pour {k}.")
            cmds.append(f"set {k} {cv}")

        if payload:
            if not _PAYLOAD_RE.match(payload):
                return ModuleResult(status="refused", detail=f"Payload invalide : {payload}")
            cmds.append(f"set PAYLOAD {payload}")
        if lhost:
            if not _HOST_RE.match(lhost):
                return ModuleResult(status="refused", detail=f"LHOST invalide : {lhost}")
            cmds.append(f"set LHOST {lhost}")
        if lport is not None:
            try:
                lp = int(lport)
                if not (1 <= lp <= 65535):
                    raise ValueError
            except (TypeError, ValueError):
                return ModuleResult(status="refused", detail="lport invalide.")
            cmds.append(f"set LPORT {lp}")

        cmds += ["run", "exit -y"]
        resource = "; ".join(cmds)
        argv = ["msfconsole", "-q", "-x", resource]

        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT)
        except subprocess.TimeoutExpired:
            return ModuleResult(status="error", detail=f"metasploit : délai dépassé ({DEFAULT_TIMEOUT}s).")
        except Exception as exc:  # noqa: BLE001
            return ModuleResult(status="error", detail=f"Échec metasploit : {exc}")

        output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
        entities = []
        if output:
            entities.append(ModuleResultEntity(
                type="other",
                value=f"metasploit {module} → {target}",
                extra={"module": module, "resource": resource, "output": output[-8000:]},
            ))
        return ModuleResult(
            status="ok", entities=entities,
            detail=f"metasploit {module} exécuté (code {proc.returncode}, {len(output)} car.).",
            raw={"resource": resource, "returncode": proc.returncode},
        )
