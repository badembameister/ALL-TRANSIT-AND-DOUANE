from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..models import User
from ..schemas import UserIn, UserOut
from ..security import current_user, hash_pwd, make_token, require, verify

router = APIRouter(tags=["Authentification et utilisateurs"])


@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == form.username))
    if not u or not u.actif or not verify(form.password, u.pwd):
        raise HTTPException(401, "Identifiants incorrects")
    return {"access_token": make_token(u), "token_type": "bearer", "role": u.role}


@router.get("/auth/me", response_model=UserOut)
def me(u: User = Depends(current_user)):
    return u


@router.get("/users", response_model=list[UserOut])
def lister(_: User = Depends(require()), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def creer(body: UserIn, admin: User = Depends(require()), db: Session = Depends(get_db)):
    if body.role == "Client" and not body.client_id:
        raise HTTPException(422, "Un utilisateur Client doit être rattaché à un client")
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "Adresse e-mail déjà utilisée")
    u = User(email=body.email, nom=body.nom, role=body.role, client_id=body.client_id, pwd=hash_pwd(body.password))
    db.add(u)
    db.flush()
    audit(db, admin, "utilisateur", u.id, "création", f"{u.email} ({u.role})")
    db.commit()
    return u
