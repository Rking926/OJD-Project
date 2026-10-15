"""Moteur d'enquête autonome (playbook).

Contrairement à `run_prompt` (piloté tour par tour par le LLM), le playbook
réalise un **fan-out déterministe** : à partir d'une cible, il lance TOUS les
connecteurs OSINT pertinents, puis **rebondit automatiquement** sur chaque
nouvelle entité exploitable (email → fuites/comptes, domaine → DNS/sous-domaines/
emails, IP → géoloc…), sur plusieurs niveaux. Avantages :
  - couverture garantie (on ne dépend pas du modèle pour penser à chaque outil) ;
  - rapide (outils en parallèle, le LLM n'est appelé qu'une fois, pour la synthèse) ;
  - sûr : seuls les modules OSINT standards sont utilisés. Les modules à schéma
    personnalisé (metasploit, recon_tool, outils utilisateur) sont exclus par
    construction — un playbook ne lance jamais d'exploit.
"""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from ..models import Entity, EntityType, Investigation, Relation, new_id
from ..modules.base import ModuleResult
from ..modules.registry import list_modules
from .orchestrator import _infer_type, _run_module
from .providers import build_provider

# Types d'entités sur lesquels on relance une recherche (rebond).
_EXPANDABLE = {"email", "domain", "ip", "username", "phone"}
_MAX_DEPTH = 2            # profondeur de rebond
_CAP_PER_TYPE = 8        # nb max d'entités re-explorées par type (anti-explosion)
_TOOL_BUDGET = 80        # nb max d'exécutions d'outils (borne coût/temps)
_PARALLEL = 5

_SYNTHESIS_SYSTEM = (
    "Tu es un analyste OSINT. On te donne le RÉSULTAT BRUT d'une enquête "
    "automatique (toutes les entités trouvées, avec leur source). Rédige un "
    "DOSSIER clair et EXHAUSTIF en français, sans rien inventer ni ajouter "
    "d'information absente des données fournies.\n"
    "Structure : 1) Résumé en 3-4 lignes. 2) Détail par catégorie "
    "(Comptes/Profils · Emails · Téléphones · Domaines & sous-domaines · "
    "Infrastructure/IP · Fuites de données · Autres). Pour chaque élément : "
    "valeur, source(s), et fiabilité (élevée si confirmé par plusieurs sources). "
    "3) Liens notables entre les éléments. 4) Pistes à creuser. Sois dense et factuel."
)


# Modules lourds/lents : on ne les lance que sur la cible initiale (depth 0),
# pas sur chaque entité découverte, pour garder l'enquête rapide.
_HEAVY = {"theharvester", "crtsh"}
# Jamais lancés automatiquement : memory (outil de recoupement interactif) et
# spiderfoot (scan très lent, à déclencher explicitement).
_SKIP_IN_PLAYBOOK = {"memory", "spiderfoot"}


def _osint_modules_for(type_value: str, mc: dict, depth: int = 0):
    """Connecteurs OSINT standards acceptant ce type ET opérationnels."""
    mods = []
    for m in list_modules():
        if m.input_schema() is not None:      # exclut metasploit/recon/outils perso
            continue
        if m.name in _SKIP_IN_PLAYBOOK:
            continue
        if type_value not in [t.value for t in getattr(m, "accepts", [])]:
            continue
        if not m.is_configured(mc):            # exclut hibp sans clé, toutatis sans session
            continue
        if depth > 0 and m.name in _HEAVY:     # lourd -> seulement sur la cible initiale
            continue
        mods.append(m)
    return mods


def run_full_investigation(db: Session, investigation: Investigation, seed_value: str,
                           seed_type: str, llm_config: dict) -> dict:
    mc = llm_config.get("module_config", {})
    inv_id = investigation.id
    seed_value = (seed_value or "").strip()
    seed_type = (seed_type or "").strip() or _infer_type(seed_value)

    # Index entités + relations (réutilise l'existant pour dédoublonner).
    entity_by_key: dict[tuple[str, str], Entity] = {
        (e.type.value if hasattr(e.type, "value") else str(e.type), e.value): e
        for e in db.query(Entity).filter(Entity.investigation_id == inv_id).all()
    }
    seen_relations: set[tuple[str, str, str]] = {
        (r.from_entity_id, r.to_entity_id, r.label)
        for r in db.query(Relation).filter(Relation.investigation_id == inv_id).all()
    }
    new_entities: list[Entity] = []

    def get_or_create(tv: str, value: str, source: str, confidence: float = 1.0,
                      extra: dict | None = None) -> tuple[Entity, bool]:
        t = tv if tv in EntityType._value2member_map_ else "other"
        key = (t, value)
        if key in entity_by_key:
            return entity_by_key[key], False
        e = Entity(id=new_id(), investigation_id=inv_id, type=EntityType(t), value=value,
                   source_module=source, confidence=confidence, extra=extra or {})
        db.add(e); entity_by_key[key] = e; new_entities.append(e)
        return e, True

    def link(parent: Entity, child: Entity, label: str) -> None:
        if not parent or not child or parent.id == child.id:
            return
        rk = (parent.id, child.id, label)
        if rk in seen_relations:
            return
        seen_relations.add(rk)
        db.add(Relation(id=new_id(), investigation_id=inv_id,
                        from_entity_id=parent.id, to_entity_id=child.id, label=label))

    seed_entity, _ = get_or_create(seed_type, seed_value, "requête:enquête")
    if not _osint_modules_for(seed_type, mc):
        return {"reply": f"Aucun connecteur OSINT ne sait exploiter une cible de type « {seed_type} ». "
                         f"Essaie un pseudo, un email, un domaine, un téléphone ou une IP.",
                "new_entities": [], "tool_calls": []}

    queue: deque = deque([(seed_type, seed_value, seed_entity, 0)])
    processed: set[tuple[str, str]] = set()
    expanded_per_type: dict[str, int] = {}
    tool_log: list[dict] = []
    runs = 0

    while queue and runs < _TOOL_BUDGET:
        typ, val, parent, depth = queue.popleft()
        if (typ, val) in processed:
            continue
        processed.add((typ, val))
        mods = _osint_modules_for(typ, mc, depth)
        if not mods:
            continue

        with ThreadPoolExecutor(max_workers=_PARALLEL) as pool:
            futs = {pool.submit(_run_module, m, {"input_type": typ, "value": val}, mc): m for m in mods}
            for fut in futs:
                m = futs[fut]
                runs += 1
                try:
                    res = fut.result()
                except Exception as exc:  # noqa: BLE001
                    res = ModuleResult(status="error", detail=str(exc))
                tool_log.append({"module": m.name, "input_type": typ, "value": val, "status": res.status})
                for ent in res.entities:
                    child, created = get_or_create(ent.type, ent.value, m.name, ent.confidence, ent.extra)
                    link(parent, child, m.name)
                    ctype = child.type.value
                    if (created and depth < _MAX_DEPTH and ctype in _EXPANDABLE
                            and expanded_per_type.get(ctype, 0) < _CAP_PER_TYPE):
                        expanded_per_type[ctype] = expanded_per_type.get(ctype, 0) + 1
                        queue.append((ctype, child.value, child, depth + 1))
        db.commit()

    # Synthèse finale : un seul appel LLM sur l'ensemble des trouvailles.
    findings = _format_findings(new_entities)
    reply = _synthesize(llm_config, seed_type, seed_value, findings, tool_log, runs)

    return {
        "reply": reply,
        "new_entities": [_ent_dict(e) for e in new_entities],
        "tool_calls": tool_log,
    }


def _format_findings(entities: list[Entity]) -> str:
    by_type: dict[str, list[str]] = {}
    for e in entities:
        t = e.type.value if hasattr(e.type, "value") else str(e.type)
        by_type.setdefault(t, []).append(f"{e.value} (source: {e.source_module})")
    lines = []
    for t, vals in by_type.items():
        lines.append(f"[{t}] ({len(vals)})")
        for v in vals[:60]:
            lines.append(f"  - {v}")
    return "\n".join(lines) or "(aucune entité trouvée)"


def _synthesize(llm_config: dict, seed_type: str, seed_value: str,
                findings: str, tool_log: list[dict], runs: int) -> str:
    ok = sum(1 for t in tool_log if t["status"] == "ok")
    header = (f"Cible : {seed_value} (type {seed_type}). {runs} exécutions d'outils "
              f"({ok} ok). Entités brutes trouvées :\n\n{findings}")
    try:
        provider = build_provider(llm_config)
        resp = provider.chat(
            messages=[{"role": "user", "content": header
                       + "\n\nRédige le dossier d'enquête à partir de ces données."}],
            tools=[], system=_SYNTHESIS_SYSTEM,
        )
        return resp.text or header
    except Exception as exc:  # noqa: BLE001 — on renvoie au moins les données brutes
        return f"(Synthèse IA indisponible : {exc})\n\n{header}"


def _ent_dict(e: Entity) -> dict:
    return {"id": e.id, "type": e.type.value if hasattr(e.type, "value") else e.type,
            "value": e.value, "source_module": e.source_module,
            "confidence": e.confidence, "extra": e.extra}
