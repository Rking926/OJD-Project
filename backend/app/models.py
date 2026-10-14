"""Modèle de données commun : entités OSINT, relations et journal d'audit.

Toutes les recherches passent par ce modèle, quel que soit le module qui a
produit l'information (sherlock, whois, LLM, etc.). Cela permet d'afficher
un graphe de relations et, plus tard, une carte, sans dépendre du module
d'origine.
"""
from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DB_PATH = "sqlite:///./data/ojd.db"


class Base(DeclarativeBase):
    pass


class EntityType(str, enum.Enum):
    USERNAME = "username"
    EMAIL = "email"
    PHONE = "phone"
    DOMAIN = "domain"
    PERSON = "person"
    LOCATION = "location"
    IP = "ip"
    URL = "url"
    OTHER = "other"


def new_id() -> str:
    return str(uuid.uuid4())


class Investigation(Base):
    """Un dossier de recherche : regroupe toutes les entités liées à une requête."""

    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text)  # motif de la recherche (traçabilité/RGPD)
    created_by: Mapped[str] = mapped_column(String, default="local-user")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    entities: Mapped[list["Entity"]] = relationship(back_populates="investigation", cascade="all, delete-orphan")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"))
    type: Mapped[EntityType] = mapped_column(Enum(EntityType))
    value: Mapped[str] = mapped_column(String, index=True)
    source_module: Mapped[str] = mapped_column(String)  # quel module a produit cette entité
    confidence: Mapped[float] = mapped_column(default=1.0)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)  # données brutes du module
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    investigation: Mapped[Investigation] = relationship(back_populates="entities")


class Relation(Base):
    """Lien entre deux entités (ex: username -> profil trouvé sur tel site)."""

    __tablename__ = "relations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"))
    from_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    to_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    label: Mapped[str] = mapped_column(String)  # ex: "profil_trouve", "lie_a"
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    import os

    os.makedirs("./data", exist_ok=True)
    Base.metadata.create_all(engine)
