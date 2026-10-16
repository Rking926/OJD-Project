"""Boucle d'orchestration : prompt utilisateur -> choix des modules -> exécution -> synthèse.

Le LLM reçoit la liste des modules OSINT comme des "tools". Il décide
lesquels appeler et avec quels arguments (type d'entité + valeur). Chaque
appel est exécuté réellement, journalisé dans l'audit, puis le résultat est
renvoyé au LLM qui peut enchaîner d'autres appels ou conclure.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from ..models import Entity, EntityType, Investigation, Relation, new_id
from ..modules.base import ModuleResult
from ..modules.registry import get_module, list_modules
from .providers import LLMProvider, build_provider

# Cache en mémoire des résultats de modules : évite de relancer une recherche
# identique (même module + mêmes arguments + même config) pendant la durée du TTL.
_CACHE_TTL = 3600  # secondes
_CACHE_MAX = 500   # nombre max d'entrées gardées (évite que le cache gonfle sans fin)
_RESULT_CACHE: dict[str, tuple[float, ModuleResult]] = {}
# Nombre max d'outils exécutés en parallèle dans un même tour.
_MAX_PARALLEL = 5

def _cache_key(name: str, args: dict, mc: dict) -> str:
    # On inclut la config des modules (mc) dans la clé : si l'utilisateur change
    # une clé API ou un sessionid, on ne ressert pas un ancien résultat « raté ».
    # Hash SHA-256 pour ne pas stocker de secrets en clair dans la clé.
    raw = json.dumps({"n": name, "a": args, "c": mc}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _cache_get(key: str) -> ModuleResult | None:
    hit = _RESULT_CACHE.get(key)
    if hit is None:
        return None
    if (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    _RESULT_CACHE.pop(key, None)  # expiré : on nettoie au passage
    return None

def _cache_put(key: str, result: ModuleResult) -> None:
    # Si le cache est plein, on purge d'abord les entrées les plus anciennes.
    if len(_RESULT_CACHE) >= _CACHE_MAX:
        oldest = sorted(_RESULT_CACHE, key=lambda k: _RESULT_CACHE[k][0])
        for k in oldest[: max(1, _CACHE_MAX // 4)]:
            _RESULT_CACHE.pop(k, None)
    _RESULT_CACHE[key] = (time.time(), result)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+$")
_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_PHONE_RE = re.compile(r"^\+?[0-9\s().-]{6,}$")

def _infer_type(value: str) -> str:
    v = value.strip()
    if _EMAIL_RE.match(v):
        return "email"
    if _IP_RE.match(v):
        return "ip"
    if _DOMAIN_RE.match(v):
        return "domain"
    if _PHONE_RE.match(v) and sum(c.isdigit() for c in v) >= 6:
        return "phone"
    return "username"

def _normalize_std_args(module, args: dict) -> tuple[str, str]:
    """Corrige les arguments mal remplis par le LLM (fréquent avec un petit
    modèle local). Les modules standards acceptent souvent un seul type d'entrée :
    on force alors ce type, et on récupère la valeur même si le LLM l'a mise dans
    une clé inattendue. Gain de précision/robustesse sans dépendre du modèle.
    """
    value = ""
    for k in ("value", "query", "target", "username", "email", "domain", "phone", "input"):
        v = args.get(k)
        if isinstance(v, str) and v.strip():
            value = v.strip()
            break

    accepts = [t.value for t in getattr(module, "accepts", [])]
    it = (args.get("input_type") or "").strip()

    # Si le LLM a mis la valeur dans input_type et laissé value vide, on récupère.
    if not value and it and it not in accepts:
        value = it

    if it not in accepts:
        if len(accepts) == 1:
            it = accepts[0]            # un seul type possible -> on l'impose
        elif accepts:
            inferred = _infer_type(value)
            it = inferred if inferred in accepts else accepts[0]
    return it, value

def _run_module(module, args: dict, mc: dict) -> ModuleResult:
    """Exécute un module (appel réseau/subprocess) sans toucher à la base.

    Fonction pure, sûre à lancer dans un thread. Les écritures DB (entités,
    audit) sont faites ensuite sur le thread principal par l'appelant.
    """
    # Clé de cache sur les arguments EFFECTIFS (normalisés pour les modules
    # standards) + la config des modules : deux appels logiquement identiques
    # mais aux arguments bruts différents (fréquent avec un LLM) tapent alors le
    # même cache -> on évite de relancer le même outil plusieurs fois.
    is_custom = module.input_schema() is not None
    if is_custom:
        key = _cache_key(module.name, args, mc)
    else:
        input_type, value = _normalize_std_args(module, args)
        key = _cache_key(module.name, {"input_type": input_type, "value": value}, mc)

    cached = _cache_get(key)
    if cached is not None:
        return cached

    if is_custom:
        result = module.run(config=mc, **args)
    else:
        result = module.run(input_type, value, mc)

    if result.status == "ok":
        _cache_put(key, result)
    return result

SYSTEM_PROMPT = (
    "Tu es l'assistant d'investigation OSINT d'une application professionnelle "
    "(sources ouvertes uniquement). Ta mission : produire des informations "
    "PRÉCISES, VÉRIFIÉES et EXHAUSTIVES sur la cible, sans JAMAIS rien inventer.\n\n"
    "MÉTHODE (systématique) :\n"
    "1. Identifie le type d'entrée (pseudo, email, téléphone, domaine, nom) et "
    "choisis TOUS les outils pertinents pour ce type — pas un seul.\n"
    "2. Lance-les (plusieurs en parallèle dans un même tour, c'est permis).\n"
    "3. RECOUPE et ENCHAÎNE : chaque info trouvée relance une recherche. Ex : un "
    "email découvert → holehe + hibp + xposedornot dessus ; un domaine → whois + "
    "recon ; un profil → exploite le pseudo associé. Continue tant que de "
    "nouvelles pistes apparaissent.\n"
    "4. Arrête-toi quand les outils n'apportent plus rien de nouveau.\n\n"
    "RÈGLES STRICTES :\n"
    "- N'affirme JAMAIS une info que les outils n'ont pas renvoyée. Aucune "
    "supposition présentée comme un fait.\n"
    "- Distingue CONFIRMÉ (trouvé par un outil) de PISTE à vérifier.\n"
    "- Si plusieurs outils confirment la même info, signale-le (fiabilité élevée).\n"
    "- Si un outil échoue/est refusé, dis-le et propose une alternative.\n\n"
    "SYNTHÈSE FINALE (toujours, en français, structurée par catégories) :\n"
    "Profils/comptes · Emails · Téléphones · Domaines · Fuites de données · Autres.\n"
    "Pour chaque élément : la valeur, la/les source(s) (outils), le niveau de "
    "fiabilité, et ses liens avec les autres éléments. Termine par les pistes non "
    "confirmées à explorer. Sois factuel, dense et utile — pas de remplissage."
)

MAX_TOOL_ROUNDS = 8

def _tools_schema() -> list[dict]:
    schema = []
    for m in list_modules():
        custom = m.input_schema()
        schema.append({
            "name": m.name,
            "description": m.description + (f" [{m.legal_notice}]" if m.legal_notice else ""),
            "input_schema": custom or {
                "type": "object",
                "properties": {
                    "input_type": {"type": "string", "enum": [t.value for t in m.accepts]},
                    "value": {"type": "string", "description": "La valeur à rechercher (ex: le pseudo, l'email, le domaine)."},
                },
                "required": ["input_type", "value"],
            },
        })
    return schema

def run_prompt(db: Session, investigation: Investigation, prompt: str, llm_config: dict) -> dict:
    """Exécute un prompt utilisateur dans le contexte d'une investigation.

    Retourne {"reply": str, "new_entities": [...], "tool_calls": [...]}.
    """
    provider: LLMProvider = build_provider(llm_config)
    tools = _tools_schema()
    messages = [{"role": "user", "content": prompt}]

    new_entities: list[Entity] = []
    tool_call_log: list[dict] = []

    # Dédoublonnage : une même entité (type + valeur) n'existe qu'une fois par
    # enquête, même si plusieurs outils la renvoient. On indexe les entités
    # existantes pour pouvoir aussi créer des relations qui les référencent.
    inv_id = investigation.id
    entity_by_key: dict[tuple[str, str], Entity] = {
        (e.type.value if hasattr(e.type, "value") else str(e.type), e.value): e
        for e in db.query(Entity).filter(Entity.investigation_id == inv_id).all()
    }
    seen_relations: set[tuple[str, str, str]] = {
        (r.from_entity_id, r.to_entity_id, r.label)
        for r in db.query(Relation).filter(Relation.investigation_id == inv_id).all()
    }

    def _get_or_create(type_value: str, value: str, source: str,
                       confidence: float = 1.0, extra: dict | None = None) -> tuple[Entity, bool]:
        tv = type_value if type_value in EntityType._value2member_map_ else "other"
        key = (tv, value)
        existing = entity_by_key.get(key)
        if existing is not None:
            return existing, False
        e = Entity(id=new_id(), investigation_id=inv_id, type=EntityType(tv),
                   value=value, source_module=source, confidence=confidence, extra=extra or {})
        db.add(e)
        entity_by_key[key] = e
        new_entities.append(e)
        return e, True

    def _link(parent: Entity, child: Entity, label: str) -> None:
        if parent is None or child is None or parent.id == child.id:
            return
        rkey = (parent.id, child.id, label)
        if rkey in seen_relations:
            return
        seen_relations.add(rkey)
        db.add(Relation(id=new_id(), investigation_id=inv_id,
                        from_entity_id=parent.id, to_entity_id=child.id, label=label))

    for _ in range(MAX_TOOL_ROUNDS):
        response = provider.chat(messages=messages, tools=tools, system=SYSTEM_PROMPT)

        if not response.tool_calls:
            return {
                "reply": response.text,
                "new_entities": [_entity_to_dict(e) for e in new_entities],
                "tool_calls": tool_call_log,
            }

        messages.append(provider.assistant_tool_use_message(response))

        mc = llm_config.get("module_config", {})

        # 1) Préparation : on résout chaque appel et on isole ceux qui sont
        #    réellement exécutables (les refus/erreurs ne lancent rien).
        planned = []  # (tc, module, args, input_type, value, runnable: bool, pre_text, pre_status)
        for tc in response.tool_calls:
            module = get_module(tc.name)
            args = tc.arguments or {}
            # Valeurs affichées (log/UI) : normalisées pour les modules standards.
            if module is not None and module.input_schema() is None:
                input_type, value = _normalize_std_args(module, args)
            else:
                input_type = args.get("input_type", args.get("tool", ""))
                value = args.get("value", args.get("target", ""))

            if module is None:
                planned.append((tc, None, args, input_type, value, False,
                                f"Module inconnu: {tc.name}", "error"))
            elif not module.is_configured(mc):
                planned.append((tc, module, args, input_type, value, False,
                                f"Module '{module.name}' non configuré ou désactivé. "
                                f"Nécessite: {module.requires_config}. {module.legal_notice}",
                                "refused"))
            else:
                planned.append((tc, module, args, input_type, value, True, None, None))

        # 2) Exécution en parallèle de tous les modules lançables de ce tour.
        runnable = [p for p in planned if p[5]]
        results: dict[str, ModuleResult] = {}
        if runnable:
            with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
                futures = {
                    pool.submit(_run_module, p[1], p[2], mc): p[0].id
                    for p in runnable
                }
                for fut in futures:
                    tc_id = futures[fut]
                    try:
                        results[tc_id] = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        results[tc_id] = ModuleResult(status="error", detail=str(exc))

        # 3) Écritures DB (entités) sur le thread principal, dans l'ordre.
        for tc, module, args, input_type, value, is_runnable, pre_text, pre_status in planned:
            if not is_runnable:
                status, result_text = pre_status, pre_text
            else:
                result = results[tc.id]
                status = result.status

                # Nœud "parent" = la cible interrogée (pseudo, email, domaine…),
                # pour relier visuellement ce qui a été trouvé à partir d'elle.
                parent = None
                if value:
                    p_type = input_type if input_type in EntityType._value2member_map_ else _infer_type(value)
                    parent, _ = _get_or_create(p_type, value, source=f"requête:{module.name}")

                added_this_call = 0
                for ent in result.entities:
                    child, created = _get_or_create(
                        ent.type, ent.value, source=module.name,
                        confidence=ent.confidence, extra=ent.extra,
                    )
                    _link(parent, child, module.name)
                    if created:
                        added_this_call += 1
                result_text = json.dumps({
                    "status": result.status,
                    "detail": result.detail,
                    "entities_found": len(result.entities),
                    "nouvelles_entites": added_this_call,
                    "entities": [{"type": e.type, "value": e.value} for e in result.entities],
                }, ensure_ascii=False)

            tool_call_log.append({"module": tc.name, "input_type": input_type, "value": value, "status": status})
            messages.append(provider.tool_result_message(tc.id, tc.name, result_text))

        db.commit()

    return {
        "reply": "Nombre maximal d'appels d'outils atteint pour cette requête.",
        "new_entities": [_entity_to_dict(e) for e in new_entities],
        "tool_calls": tool_call_log,
    }

def _entity_to_dict(e: Entity) -> dict:
    return {
        "id": e.id,
        "type": e.type.value if hasattr(e.type, "value") else e.type,
        "value": e.value,
        "source_module": e.source_module,
        "confidence": e.confidence,
        "extra": e.extra,
    }
