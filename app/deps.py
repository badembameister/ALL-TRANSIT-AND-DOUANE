from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .audit import audit  # noqa: F401  (réexport)
from .customs import DEFAULT_PARAMS
from .db import get_db
from .models import Dossier, Param, User
from .security import current_user


def get_params(db: Session) -> dict:
    p = db.get(Param, "douane")
    return p.value if p else DEFAULT_PARAMS


def dossier_for(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Dossier:
    d = db.get(Dossier, did)
    if not d or (user.role == "Client" and d.client_id != user.client_id):
        raise HTTPException(404, "Dossier introuvable")
    return d
