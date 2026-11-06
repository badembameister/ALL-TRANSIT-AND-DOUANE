import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

SECRET = os.getenv("SECRET_KEY", "dev-only-change-me-please-0123456789abcdef")
if os.getenv("VERCEL") and not os.getenv("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY doit être défini dans les variables d'environnement Vercel")
ROLES = ["Administrateur", "Responsable transit", "Déclarant en douane", "Agent opérationnel",
         "Comptable", "Commercial", "Client", "Direction"]
STAFF = tuple(r for r in ROLES if r != "Client")
W_DOSSIER = ("Responsable transit",)
W_DOCS = ("Responsable transit", "Agent opérationnel", "Déclarant en douane")
W_TRANSIT = ("Responsable transit", "Agent opérationnel")
W_DOUANE = ("Responsable transit", "Déclarant en douane")
W_OPS = ("Responsable transit", "Agent opérationnel")
W_FACT = ("Comptable",)
W_CLIENT = ("Commercial", "Responsable transit")
bearer = OAuth2PasswordBearer(tokenUrl="auth/login")


def hash_pwd(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify(p: str, h: str) -> bool:
    return bcrypt.checkpw(p.encode(), h.encode())


def make_token(u: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    return jwt.encode({"sub": str(u.id), "exp": exp}, SECRET, algorithm="HS256")


def current_user(token: str = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        sub = int(jwt.decode(token, SECRET, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Jeton invalide ou expiré")
    u = db.get(User, sub)
    if not u or not u.actif:
        raise HTTPException(401, "Utilisateur inconnu ou désactivé")
    return u


def require(*roles: str):
    """Autorise les rôles listés ; l'administrateur a toujours accès."""
    def dep(u: User = Depends(current_user)) -> User:
        if u.role != "Administrateur" and u.role not in roles:
            raise HTTPException(403, "Droits insuffisants pour cette action")
        return u
    return dep
