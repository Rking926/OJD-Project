"""Module mémoire : base de connaissance accumulée entre toutes les enquêtes.

Interroge l'historique : est-ce qu'une valeur (email, pseudo, domaine, IP…) a
déjà été rencontrée dans de précédentes enquêtes ? Si oui, où, par quel outil,
et avec quelles entités liées. C'est ce qui rend l'app « de plus en plus
précise » : plus tu l'utilises, plus elle recoupe.

Lecture seule sur la base locale (aucune donnée ne sort de la machine).
"""
from __future__ import annotations

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule


class MemoryModule(OsintModule):
    name = "memory"
    description = (
        "Base de connaissance interne : indique si une valeur (email, pseudo, "
        "domaine, IP, téléphone…) a déjà été vue dans de précédentes enquêtes, "
        "et renvoie le contexte (outils l'ayant trouvée, entités liées). "
        "À utiliser pour recouper avec l'historique."
    )
    accepts = [InputType.USERNAME, InputType.EMAIL, InputType.PHONE,
               InputType.DOMAIN, InputType.IP, InputType.NAME]
    legal_notice = "Lecture de la base locale uniquement."

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        value = (value or "").strip()
        if not value:
            return ModuleResult(status="refused", detail="Valeur à rechercher manquante.")

        from ..models import Entity, Investigation, Relation, SessionLocal

        db = SessionLocal()
        try:
            rows = db.query(Entity).filter(Entity.value == value).all()
            if not rows:
                return ModuleResult(status="ok", entities=[],
                                    detail=f"« {value} » : jamais rencontré dans les enquêtes précédentes.")

            inv_ids = {e.investigation_id for e in rows}
            inv_titles = {
                i.id: i.title
                for i in db.query(Investigation).filter(Investigation.id.in_(inv_ids)).all()
            }
            sources = sorted({e.source_module for e in rows})

            # Entités liées (dans les mêmes enquêtes) pour donner du contexte.
            linked: list[ModuleResultEntity] = []
            seen = set()
            for e in rows:
                rels = db.query(Relation).filter(
                    (Relation.from_entity_id == e.id) | (Relation.to_entity_id == e.id)
                ).all()
                other_ids = {r.to_entity_id for r in rels} | {r.from_entity_id for r in rels}
                other_ids.discard(e.id)
                for oe in db.query(Entity).filter(Entity.id.in_(other_ids)).all():
                    k = (oe.type.value if hasattr(oe.type, "value") else str(oe.type), oe.value)
                    if k in seen:
                        continue
                    seen.add(k)
                    linked.append(ModuleResultEntity(
                        type=k[0], value=oe.value,
                        extra={"source": "memory", "lie_a": value, "via": oe.source_module},
                    ))

            summary = ModuleResultEntity(
                type="other",
                value=f"« {value} » déjà vu dans {len(inv_ids)} enquête(s)",
                extra={
                    "source": "memory",
                    "occurrences": len(rows),
                    "enquetes": [inv_titles.get(i, i) for i in inv_ids],
                    "trouve_par": sources,
                    "entites_liees": len(linked),
                },
            )
            detail = (f"« {value} » connu : {len(rows)} occurrence(s) dans "
                      f"{len(inv_ids)} enquête(s), via {', '.join(sources)}. "
                      f"{len(linked)} entité(s) liée(s).")
            return ModuleResult(status="ok", entities=[summary, *linked[:30]], detail=detail)
        finally:
            db.close()
