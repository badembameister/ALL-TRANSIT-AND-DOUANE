import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .customs import DEFAULT_PARAMS
from .db import Base, SessionLocal, engine, sync_columns
from .models import Param, User
from .routes import admin, auth, clients, dossiers, douane, finance, operations, transit
from .security import hash_pwd

_ready = False


def init_db() -> None:
    """Crée les tables, les paramètres et le compte administrateur s'ils manquent. Idempotent."""
    global _ready
    if _ready:
        return
    password = os.getenv("ADMIN_PASSWORD")
    if os.getenv("VERCEL") and not password:
        raise RuntimeError("ADMIN_PASSWORD doit être défini dans les variables d'environnement Vercel")
    Base.metadata.create_all(engine)
    sync_columns()
    email = os.getenv("ADMIN_EMAIL", "admin@alliance.local").strip().lower()
    try:
        with SessionLocal() as db:
            if not db.get(Param, "douane"):
                db.add(Param(key="douane", value=DEFAULT_PARAMS))
            if not db.scalar(select(User).where(func.lower(User.email) == email)):
                db.add(User(email=email, nom="Administrateur", role="Administrateur",
                            pwd=hash_pwd(password or "ChangeMe!2026")))
            db.commit()
    except IntegrityError:  # deux démarrages à froid simultanés : l'autre a déjà créé les lignes
        pass
    _ready = True


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Alliance Transit API", version="0.2.0", lifespan=lifespan,
              description="Gestion du transit, du transport et de la douane (Guinée).")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def prete(request, call_next):  # sur Vercel, le lifespan d'une application montée ne s'exécute pas
    init_db()
    return await call_next(request)


for r in (auth, clients, dossiers, transit, douane, finance, operations, admin):
    app.include_router(r.router)


@app.get("/health", tags=["Technique"])
def health():
    return {"status": "ok"}
