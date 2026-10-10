"""API FastAPI de l'application OSINT.

Lancement:
    uvicorn app.main:app --reload --port 8000

Sert aussi la petite UI statique (frontend/) pour le MVP.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config_store import load_config, public_config, save_config
from .models import AuditEvent, Entity, Investigation, Relation, SessionLocal, init_db
from .modules.registry import manifests
from .orchestrator.orchestrator import run_prompt

app = FastAPI(title="OJD OSINT", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


# ---------- Modules ----------

@app.get("/api/modules")
def api_list_modules():
    return manifests()


# ---------- Config ----------

class ConfigIn(BaseModel):
    llm_provider: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    ollama_model: str | None = None
    ollama_base_url: str | None = None
    module_config: dict | None = None


@app.get("/api/config")
def api_get_config():
    return public_config(load_config())


@app.put("/api/config")
def api_put_config(body: ConfigIn):
    config = load_config()
    data = body.model_dump(exclude_none=True)
    module_config = data.pop("module_config", None)
    config.update(data)
    if module_config:
        config["module_config"] = {**config.get("module_config", {}), **module_config}
    save_config(config)
    return public_config(config)


# ---------- Investigations ----------

class InvestigationIn(BaseModel):
    title: str
    reason: str


@app.post("/api/investigations")
def api_create_investigation(body: InvestigationIn):
    if not body.reason.strip():
        raise HTTPException(400, "Le motif de la recherche est obligatoire (traçabilité).")
    db = SessionLocal()
    try:
        inv = Investigation(title=body.title, reason=body.reason)
        db.add(inv)
        db.commit()
        return {"id": inv.id, "title": inv.title, "reason": inv.reason, "created_at": str(inv.created_at)}
    finally:
        db.close()


@app.get("/api/investigations")
def api_list_investigations():
    db = SessionLocal()
    try:
        rows = db.query(Investigation).order_by(Investigation.created_at.desc()).all()
        return [
            {"id": i.id, "title": i.title, "reason": i.reason, "created_at": str(i.created_at)}
            for i in rows
        ]
    finally:
        db.close()


@app.get("/api/investigations/{inv_id}")
def api_get_investigation(inv_id: str):
    db = SessionLocal()
    try:
        inv = db.get(Investigation, inv_id)
        if not inv:
            raise HTTPException(404, "Investigation introuvable.")
        entities = db.query(Entity).filter(Entity.investigation_id == inv_id).all()
        relations = db.query(Relation).filter(Relation.investigation_id == inv_id).all()
        audit = db.query(AuditEvent).filter(AuditEvent.investigation_id == inv_id).order_by(AuditEvent.created_at).all()
        return {
            "id": inv.id,
            "title": inv.title,
            "reason": inv.reason,
            "entities": [
                {"id": e.id, "type": e.type.value, "value": e.value, "source_module": e.source_module,
                 "confidence": e.confidence, "extra": e.extra}
                for e in entities
            ],
            "relations": [
                {"id": r.id, "from": r.from_entity_id, "to": r.to_entity_id, "label": r.label}
                for r in relations
            ],
            "audit": [
                {"module": a.module, "input_value": a.input_value, "status": a.status,
                 "detail": a.detail, "created_at": str(a.created_at)}
                for a in audit
            ],
        }
    finally:
        db.close()


# ---------- Prompt (texte ou transcrit depuis la voix) ----------

class PromptIn(BaseModel):
    investigation_id: str
    prompt: str


@app.post("/api/prompt")
def api_prompt(body: PromptIn):
    db = SessionLocal()
    try:
        inv = db.get(Investigation, body.investigation_id)
        if not inv:
            raise HTTPException(404, "Investigation introuvable.")
        config = load_config()
        try:
            result = run_prompt(db, inv, body.prompt, config)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return result
    finally:
        db.close()


# ---------- Frontend statique ----------

_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
