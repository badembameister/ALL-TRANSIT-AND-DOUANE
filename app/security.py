import logging
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from sqlalchemy import delete, func, select

from .db import PROD, get_db
from .models import Tentative, User

_DEV_SECRET = "dev-only-change-me-please-0123456789abcdef"
SECRET = os.getenv("SECRET_KEY", "").strip() or _DEV_SECRET
if PROD and SECRET == _DEV_SECRET:
    raise RuntimeError("SECRET_KEY doit être défini (variables d'environnement) : générez-le avec « openssl rand -hex 32 »")
if PROD and len(SECRET) < 32:
    logging.getLogger("alliance").warning("SECRET_KEY trop court (%d caractères) : utilisez « openssl rand -hex 32 »", len(SECRET))
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
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except ValueError:  # mot de passe de plus de 72 octets ou empreinte illisible
        return False


_leurre = ""


def verify_leurre(p: str) -> None:
    """Même temps de calcul que pour un compte existant : la durée de réponse ne révèle pas si l'adresse est connue."""
    global _leurre
    _leurre = _leurre or hash_pwd("leurre-sans-compte")
    verify(p[:60], _leurre)


def make_token(u: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    return jwt.encode({"sub": str(u.id), "v": u.jeton_v or 0, "exp": exp}, SECRET, algorithm="HS256")


def current_user(token: str = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        data = jwt.decode(token, SECRET, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        sub, version = int(data["sub"]), int(data.get("v", 0))
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise HTTPException(401, "Jeton invalide ou expiré")
    u = db.get(User, sub)
    if not u or not u.actif:
        raise HTTPException(401, "Utilisateur inconnu ou désactivé")
    if version != (u.jeton_v or 0):  # mot de passe changé depuis : les anciennes sessions sont fermées
        raise HTTPException(401, "Session expirée : reconnectez-vous")
    return u


# ---------- Limitation des essais (connexion, mot de passe actuel) ----------

FENETRE = timedelta(minutes=15)
MAX_PAR_COMPTE = 8   # échecs par adresse e-mail sur la fenêtre
MAX_PAR_IP = 30      # échecs par adresse IP sur la fenêtre


def _maintenant() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def adresse_ip(request) -> str:
    """Adresse du client. L'en-tête x-forwarded-for n'est cru que sur Vercel, qui le réécrit lui-même."""
    if os.getenv("VERCEL"):
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()[:60]
    return (request.client.host if request.client else "inconnue")[:60]


def verifier_essais(db: Session, limites: dict[str, int]) -> None:
    """Refuse (429) si l'une des clés a dépassé son nombre d'échecs récents."""
    depuis = _maintenant() - FENETRE
    for cle, maxi in limites.items():
        n = db.scalar(select(func.count()).select_from(Tentative).where(Tentative.cle == cle, Tentative.ts > depuis))
        if n >= maxi:
            raise HTTPException(429, "Trop d'essais. Réessayez dans 15 minutes.",
                                headers={"Retry-After": str(int(FENETRE.total_seconds()))})


def noter_echec(db: Session, *cles: str) -> None:
    db.rollback()
    db.execute(delete(Tentative).where(Tentative.ts < _maintenant() - FENETRE))
    db.add_all([Tentative(cle=c, ts=_maintenant()) for c in cles])
    db.commit()


def oublier_echecs(db: Session, cle: str) -> None:
    db.execute(delete(Tentative).where(Tentative.cle == cle))


def require(*roles: str):
    """Autorise les rôles listés ; l'administrateur a toujours accès."""
    def dep(u: User = Depends(current_user)) -> User:
        if u.role != "Administrateur" and u.role not in roles:
            raise HTTPException(403, "Droits insuffisants pour cette action")
        return u
    return dep
