"""Tests du garde-fou de périmètre labo + validations du module Metasploit.

Ne lancent JAMAIS msfconsole : on vérifie uniquement les chemins de refus
(validation des entrées + périmètre) qui retournent avant tout subprocess,
plus le périmètre strict lui-même.

Exécuter depuis backend/ :  PYTHONPATH=. python -m pytest tests/ -q
ou simplement :             PYTHONPATH=. python tests/test_lab_scope.py
"""
from __future__ import annotations

from app.modules.metasploit_module import MetasploitModule
from app.modules.registry import manifests
from app.sandbox import in_scope_strict


def test_strict_scope_loopback_ok():
    assert in_scope_strict("127.0.0.1", {"sandbox": {}})[0] is True
    assert in_scope_strict("localhost", {"sandbox": {}})[0] is True
    assert in_scope_strict("127.0.0.1:2222", {"sandbox": {}})[0] is True


def test_strict_scope_refuses_lan_and_public_by_default():
    # Pas de périmètre explicite => LAN domestique et IP publique refusés.
    assert in_scope_strict("192.168.1.10", {"sandbox": {"scope": []}})[0] is False
    assert in_scope_strict("8.8.8.8", {"sandbox": {"scope": []}})[0] is False


def test_strict_scope_explicit_allows():
    cfg = {"sandbox": {"scope": ["192.168.56.0/24", ".lab"]}}
    assert in_scope_strict("192.168.56.10", cfg)[0] is True
    assert in_scope_strict("cible.lab", cfg)[0] is True
    # Une autre IP privée hors du périmètre déclaré reste refusée.
    assert in_scope_strict("192.168.1.10", cfg)[0] is False


def test_metasploit_requires_params():
    m = MetasploitModule()
    assert m.run(module="", target="").status == "refused"


def test_metasploit_rejects_bad_module_name():
    m = MetasploitModule()
    r = m.run(module="rm -rf /", target="127.0.0.1")
    assert r.status == "refused"
    r2 = m.run(module="exploit/x; drop", target="127.0.0.1")
    assert r2.status == "refused"


def test_metasploit_rejects_option_injection():
    m = MetasploitModule()
    r = m.run(
        module="auxiliary/scanner/portscan/tcp",
        target="127.0.0.1",
        options={"FOO": "bar; exploit"},  # ';' interdit (anti-injection)
    )
    assert r.status == "refused"


def test_metasploit_refuses_out_of_scope_target():
    m = MetasploitModule()
    # 192.168.1.10 n'est pas loopback et aucun scope explicite -> refusé,
    # AVANT tout lancement de msfconsole.
    r = m.run(module="auxiliary/scanner/portscan/tcp", target="192.168.1.10")
    assert r.status == "refused"
    assert "non autorisée" in r.detail or "périmètre" in r.detail


def test_registry_exposes_metasploit():
    names = [mf["name"] for mf in manifests()]
    assert "metasploit" in names


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    ok = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            ok += 1
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e!r}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {e!r}")
    print(f"\n{ok}/{len(fns)} tests OK")
