import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .customs import DEFAULT_PARAMS
from .db import PROD, Base, SessionLocal, engine, sync_columns
from .models import Param, User
from .routes import admin, auth, clients, dossiers, douane, finance, operations, pilotage, portail, transit
from .security import hash_pwd

_ready = False
MDP_DEV = "ChangeMe!2026"  # mot de passe administrateur du poste de développement (SQLite) : refusé en production
# En production, la documentation interactive (liste complète des routes) n'est publiée que sur demande : API_DOCS=1.
DOCS = not PROD or os.getenv("API_DOCS", "").lower() in ("1", "true", "oui")


def init_db() -> None:
    """Crée les tables, les paramètres et le compte administrateur s'ils manquent. Idempotent."""
    global _ready
    if _ready:
        return
    password = os.getenv("ADMIN_PASSWORD")
    if PROD and (not password or password == MDP_DEV):
        raise RuntimeError("ADMIN_PASSWORD doit être défini (variables d'environnement), avec une valeur qui vous est propre")
    Base.metadata.create_all(engine)
    sync_columns()
    email = os.getenv("ADMIN_EMAIL", "admin@alliance.local").strip().lower()
    try:
        with SessionLocal() as db:
            if not db.get(Param, "douane"):
                db.add(Param(key="douane", value=DEFAULT_PARAMS))
            if not db.scalar(select(User).where(func.lower(User.email) == email)):
                db.add(User(email=email, nom="Administrateur", role="Administrateur",
                            pwd=hash_pwd(password or MDP_DEV)))
            db.commit()
    except IntegrityError:  # deux démarrages à froid simultanés : l'autre a déjà créé les lignes
        pass
    _ready = True


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Alliance Transit API", version="0.2.0", lifespan=lifespan,
              description="Gestion du transit, du transport et de la douane (Guinée).",
              docs_url="/docs" if DOCS else None, redoc_url="/redoc" if DOCS else None,
              openapi_url="/openapi.json" if DOCS else None)
app.add_middleware(CORSMiddleware,
                   allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
                                  if o.strip() and o.strip() != "*"],
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])
PAGES_DOC = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def prete(request, call_next):  # sur Vercel, le lifespan d'une application montée ne s'exécute pas
    init_db()
    rep = await call_next(request)
    h = rep.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "no-referrer")
    h.setdefault("Cache-Control", "no-store")  # réponses nominatives : jamais dans un cache partagé ni sur disque
    if not request.url.path.endswith(PAGES_DOC):  # l'API ne sert que des données : rien ne doit s'y exécuter
        h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    if PROD:
        h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return rep


for r in (auth, clients, dossiers, transit, douane, finance, operations, admin, pilotage, portail):
    app.include_router(r.router)


@app.get("/health", tags=["Technique"])
def health():
    return {"status": "ok"}
