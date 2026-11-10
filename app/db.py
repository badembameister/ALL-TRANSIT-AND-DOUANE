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
# Production : Vercel, ou toute base autre que le SQLite de développement. Les valeurs par défaut y sont refusées.
PROD = SERVERLESS or not URL.startswith("sqlite")
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


class MigrationError(RuntimeError):
    """Une colonne attendue par le code n'a pas pu être ajoutée à la base."""


def _colonnes_manquantes() -> dict[str, list]:
    insp = inspect(engine)  # nouvel inspecteur : pas de cache des colonnes
    manquantes: dict[str, list] = {}
    for table in Base.metadata.sorted_tables:
        if insp.has_table(table.name):
            existantes = {c["name"] for c in insp.get_columns(table.name)}
            cols = [col for col in table.columns if col.name not in existantes]
            if cols:
                manquantes[table.name] = cols
    return manquantes


def sync_columns() -> list[str]:
    """Ajoute aux tables existantes les colonnes déclarées dans les modèles mais absentes de la base.
    Migration minimale et idempotente (pas d'Alembic pour l'instant) : uniquement des ajouts, jamais de suppression.
    Après coup, vérifie que toutes les colonnes existent ; sinon lève MigrationError (l'API refuse alors de servir)."""
    ajouts, erreurs = [], {}
    pg = engine.dialect.name == "postgresql"
    for table, cols in _colonnes_manquantes().items():
        for col in cols:
            ddl = (f"ALTER TABLE {table} ADD COLUMN {'IF NOT EXISTS ' if pg else ''}{col.name} "
                   f"{col.type.compile(engine.dialect)}")
            if col.server_default is not None:
                ddl += f" DEFAULT '{col.server_default.arg}'"
            try:
                with engine.begin() as cx:
                    cx.execute(text(ddl))
                ajouts.append(f"{table}.{col.name}")
            except DBAPIError as e:  # peut venir d'un démarrage concurrent : on tranche à la vérification
                erreurs[f"{table}.{col.name}"] = str(e.orig).strip().splitlines()[0] if e.orig else str(e)
    if ajouts:
        print(f"[migration] colonnes ajoutées : {', '.join(ajouts)}", flush=True)
    restantes = [f"{t}.{c.name}" for t, cols in _colonnes_manquantes().items() for c in cols]
    if restantes:
        detail = "; ".join(f"{k} ({erreurs[k]})" if k in erreurs else k for k in restantes)
        raise MigrationError(f"Migration incomplète, colonnes absentes de la base : {detail}")
    return ajouts
