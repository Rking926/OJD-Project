"""Boucle d'orchestration : prompt utilisateur -> choix des modules -> exécution -> synthèse.

Le LLM reçoit la liste des modules OSINT comme des "tools". Il décide
lesquels appeler et avec quels arguments (type d'entité + valeur). Chaque
appel est exécuté réellement, journalisé dans l'audit, puis le résultat est
renvoyé au LLM qui peut enchaîner d'autres appels ou conclure.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ..models import AuditEvent, Entity, EntityType, Investigation
from ..modules.registry import get_module, list_modules
from .providers import LLMProvider, build_provider

SYSTEM_PROMPT = (
    "Tu es l'assistant d'une application d'investigation OSINT (recherche en sources "
    "ouvertes), utilisée par des professionnels habilités. Pour chaque demande de "
    "l'utilisateur, décide quels outils (modules) appeler, avec quelle valeur d'entrée "
    "(username, email, phone, domain...). N'invente jamais de résultat : base-toi "
    "uniquement sur ce que les outils renvoient. Si un outil est refusé ou mal "
    "configuré, explique pourquoi à l'utilisateur. Termine toujours par un résumé "
    "clair des entités trouvées (profils, emails, domaines liés, etc.) en français."
)

MAX_TOOL_ROUNDS = 6


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

    for _ in range(MAX_TOOL_ROUNDS):
        response = provider.chat(messages=messages, tools=tools, system=SYSTEM_PROMPT)

        if not response.tool_calls:
            return {
                "reply": response.text,
                "new_entities": [_entity_to_dict(e) for e in new_entities],
                "tool_calls": tool_call_log,
            }

        messages.append(provider.assistant_tool_use_message(response))

        for tc in response.tool_calls:
            module = get_module(tc.name)
            args = tc.arguments or {}
            # Convention standard {input_type, value} ou spécifique {tool, target}.
            input_type = args.get("input_type", args.get("tool", ""))
            value = args.get("value", args.get("target", ""))

            if module is None:
                result_text = f"Module inconnu: {tc.name}"
                status = "error"
            elif not module.is_configured(llm_config.get("module_config", {})):
                result_text = (
                    f"Module '{module.name}' non configuré ou désactivé. "
                    f"Nécessite: {module.requires_config}. {module.legal_notice}"
                )
                status = "refused"
            else:
                mc = llm_config.get("module_config", {})
                if module.input_schema() is not None:
                    result = module.run(config=mc, **args)
                else:
                    result = module.run(input_type, value, mc)
                status = result.status
                for ent in result.entities:
                    db_entity = Entity(
                        investigation_id=investigation.id,
                        type=EntityType(ent.type) if ent.type in EntityType._value2member_map_ else EntityType.OTHER,
                        value=ent.value,
                        source_module=module.name,
                        confidence=ent.confidence,
                        extra=ent.extra,
                    )
                    db.add(db_entity)
                    new_entities.append(db_entity)
                result_text = json.dumps({
                    "status": result.status,
                    "detail": result.detail,
                    "entities_found": len(result.entities),
                    "entities": [{"type": e.type, "value": e.value} for e in result.entities],
                }, ensure_ascii=False)

            db.add(AuditEvent(
                investigation_id=investigation.id,
                module=tc.name,
                action="run",
                input_value=f"{input_type}:{value}",
                status=status,
                detail=result_text[:2000],
            ))
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
