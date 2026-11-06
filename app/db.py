import os

from sqlalchemy import create_engine
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
