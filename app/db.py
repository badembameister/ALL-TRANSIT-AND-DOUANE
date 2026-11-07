import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "sqlite:///./alliance.db"
# Neon, Supabase et Vercel fournissent postgres:// ou postgresql:// : on force le pilote psycopg 3.
for old in ("postgres://", "postgresql://"):
    if URL.startswith(old):
        URL = "postgresql+psycopg://" + URL[len(old):]
SERVERLESS = bool(os.getenv("VERCEL"))
engine = create_engine(
    URL,
    connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {},
    poolclass=NullPool if SERVERLESS else None,  # une connexion par appel, le pooler du fournisseur fait le reste
    pool_pre_ping=not SERVERLESS,
)
SessionLocal = sessionmaker(engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def sync_columns() -> list[str]:
    """Ajoute aux tables existantes les colonnes déclarées dans les modèles mais absentes de la base.
    Migration minimale et idempotente (pas d'Alembic pour l'instant) : uniquement des ajouts, jamais de suppression."""
    ajouts = []
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existantes = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existantes:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}"
            if col.server_default is not None:
                ddl += f" DEFAULT '{col.server_default.arg}'"
            try:
                with engine.begin() as cx:
                    cx.execute(text(ddl))
                ajouts.append(f"{table.name}.{col.name}")
            except DBAPIError:  # démarrage à froid concurrent : la colonne vient d'être ajoutée ailleurs
                pass
    return ajouts
