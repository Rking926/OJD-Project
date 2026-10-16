"""API FastAPI de l'application OSINT.

Lancement:
    uvicorn app.main:app --reload --port 8000

Sert aussi la petite UI statique (frontend/) pour le MVP.
"""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config_store import load_config, public_config, save_config
from .models import Entity, Investigation, Message, Relation, SessionLocal, init_db
from .modules.registry import manifests
from .orchestrator.orchestrator import run_prompt

app = FastAPI(title="OJD OSINT", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_stale_frontend(request, call_next):
    # Le navigateur revalide l'UI à chaque chargement (ETag) : une mise à jour
    # du frontend s'affiche tout de suite au lieu d'une vieille copie en cache.
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.on_event("startup")
def _startup() -> None:
    init_db()


# ---------- Modules ----------

@app.get("/api/modules")
def api_list_modules():
    return manifests()


# ---------- Catalogue Kali ----------

@app.get("/api/catalog")
def api_catalog():
    from .catalog_store import catalog, stats
    return {"stats": stats(), "tools": catalog()}


# ---------- Outils ajoutés par l'utilisateur (plugins) ----------

@app.get("/api/tools")
def api_list_tools():
    from .user_tools_store import load_tools
    return load_tools()


@app.post("/api/tools")
def api_add_tool(body: dict):
    from .user_tools_store import add_tool
    try:
        return add_tool(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.put("/api/tools/{name}")
def api_update_tool(name: str, body: dict):
    from .user_tools_store import update_tool
    try:
        return update_tool(name, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/tools/{name}")
def api_delete_tool(name: str):
    from .user_tools_store import delete_tool
    if not delete_tool(name):
        raise HTTPException(404, "Outil introuvable.")
    return {"deleted": name}


# ---------- Sandbox / périmètre labo ----------

@app.get("/api/sandbox")
def api_sandbox():
    from .sandbox import backend_status
    return backend_status(load_config())


# ---------- Config ----------

class ConfigIn(BaseModel):
    llm_provider: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    ollama_model: str | None = None
    ollama_base_url: str | None = None
    module_config: dict | None = None
    sandbox: dict | None = None


@app.get("/api/config")
def api_get_config():
    return public_config(load_config())


@app.put("/api/config")
def api_put_config(body: ConfigIn):
    config = load_config()
    data = body.model_dump(exclude_none=True)
    module_config = data.pop("module_config", None)
    sandbox = data.pop("sandbox", None)
    config.update(data)
    if module_config:
        config["module_config"] = {**config.get("module_config", {}), **module_config}
    if sandbox:
        config["sandbox"] = {**config.get("sandbox", {}), **sandbox}
    save_config(config)
    return public_config(config)


# ---------- Investigations ----------

class InvestigationIn(BaseModel):
    title: str = ""
    reason: str = ""


@app.post("/api/investigations")
def api_create_investigation(body: InvestigationIn):
    db = SessionLocal()
    try:
        inv = Investigation(
            title=body.title.strip() or "Nouveau chat",
            reason=body.reason.strip() or "non spécifié",
        )
        db.add(inv)
        db.commit()
        return {"id": inv.id, "title": inv.title, "reason": inv.reason, "created_at": str(inv.created_at)}
    finally:
        db.close()


class RenameIn(BaseModel):
    title: str


@app.put("/api/investigations/{inv_id}")
def api_rename_investigation(inv_id: str, body: RenameIn):
    db = SessionLocal()
    try:
        inv = db.get(Investigation, inv_id)
        if not inv:
            raise HTTPException(404, "Chat introuvable.")
        inv.title = body.title.strip() or inv.title
        db.commit()
        return {"id": inv.id, "title": inv.title}
    finally:
        db.close()


@app.delete("/api/investigations/{inv_id}")
def api_delete_investigation(inv_id: str):
    db = SessionLocal()
    try:
        inv = db.get(Investigation, inv_id)
        if not inv:
            raise HTTPException(404, "Chat introuvable.")
        # Les relations pointent vers les entités : on les supprime d'abord.
        db.query(Relation).filter(Relation.investigation_id == inv_id).delete()
        db.delete(inv)  # entités et messages suivent (cascade delete-orphan)
        db.commit()
        return {"deleted": inv_id}
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
            "messages": [
                {"role": m.role, "content": m.content, "tool_calls": m.tool_calls or [],
                 "duration_ms": m.duration_ms, "created_at": str(m.created_at)}
                for m in db.query(Message).filter(Message.investigation_id == inv_id)
                .order_by(Message.created_at).all()
            ],
        }
    finally:
        db.close()


# ---------- Prompt (texte ou transcrit depuis la voix) ----------

class PromptIn(BaseModel):
    investigation_id: str
    prompt: str


def _run_and_record(db, inv_id: str, user_text: str, run) -> dict:
    """Enregistre le message, exécute `run()` et enregistre la réponse (ou l'erreur),
    pour pouvoir réafficher la conversation quand on la rouvre."""
    db.add(Message(investigation_id=inv_id, role="user", content=user_text))
    db.commit()
    started = time.monotonic()
    try:
        result = run()
    except Exception as exc:
        db.rollback()
        db.add(Message(investigation_id=inv_id, role="error", content=str(exc),
                       duration_ms=int((time.monotonic() - started) * 1000)))
        db.commit()
        if isinstance(exc, ValueError):
            raise HTTPException(400, str(exc))
        raise
    db.add(Message(investigation_id=inv_id, role="assistant", content=result.get("reply") or "",
                   tool_calls=result.get("tool_calls") or [],
                   duration_ms=int((time.monotonic() - started) * 1000)))
    db.commit()
    return result


@app.post("/api/prompt")
def api_prompt(body: PromptIn):
    db = SessionLocal()
    try:
        inv = db.get(Investigation, body.investigation_id)
        if not inv:
            raise HTTPException(404, "Investigation introuvable.")
        config = load_config()
        return _run_and_record(db, inv.id, body.prompt, lambda: run_prompt(db, inv, body.prompt, config))
    finally:
        db.close()


# ---------- Enquête autonome (playbook) ----------

class PlaybookIn(BaseModel):
    investigation_id: str
    seed_value: str
    seed_type: str = ""  # vide => détecté automatiquement


@app.post("/api/playbook")
def api_playbook(body: PlaybookIn):
    from .orchestrator.playbooks import run_full_investigation
    db = SessionLocal()
    try:
        inv = db.get(Investigation, body.investigation_id)
        if not inv:
            raise HTTPException(404, "Investigation introuvable.")
        config = load_config()
        return _run_and_record(
            db, inv.id, f"🔎 Enquête complète sur : {body.seed_value}",
            lambda: run_full_investigation(db, inv, body.seed_value, body.seed_type, config),
        )
    finally:
        db.close()


# ---------- Frontend statique ----------

_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
