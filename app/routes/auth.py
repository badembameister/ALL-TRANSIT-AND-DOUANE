from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..models import Client, User
from ..schemas import ChangePwdIn, PasswordIn, UserIn, UserOut, UserPatch
from ..security import current_user, hash_pwd, make_token, require, verify

router = APIRouter(tags=["Authentification et utilisateurs"])


def _par_email(db: Session, email: str):
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def _client_ok(db: Session, role: str, client_id):
    if role == "Client":
        if not client_id or not db.get(Client, client_id):
            raise HTTPException(422, "Un utilisateur Client doit être rattaché à un client existant")


@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = _par_email(db, form.username)
    if not u or not u.actif or not verify(form.password, u.pwd):
        raise HTTPException(401, "Identifiants incorrects")
    return {"access_token": make_token(u), "token_type": "bearer", "role": u.role}


@router.get("/auth/me", response_model=UserOut)
def me(u: User = Depends(current_user)):
    return u


@router.post("/auth/change-password", status_code=204)
def changer_mot_de_passe(body: ChangePwdIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify(body.ancien, u.pwd):
        raise HTTPException(403, "Mot de passe actuel incorrect")
    u.pwd = hash_pwd(body.nouveau)
    audit(db, u, "utilisateur", u.id, "changement de mot de passe")
    db.commit()
    return Response(status_code=204)


@router.get("/users", response_model=list[UserOut])
def lister(_: User = Depends(require()), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def creer(body: UserIn, admin: User = Depends(require()), db: Session = Depends(get_db)):
    _client_ok(db, body.role, body.client_id)
    if _par_email(db, body.email):
        raise HTTPException(409, "Adresse e-mail déjà utilisée")
    u = User(email=body.email, nom=body.nom, role=body.role, pwd=hash_pwd(body.password),
             client_id=body.client_id if body.role == "Client" else None)
    db.add(u)
    db.flush()
    audit(db, admin, "utilisateur", u.id, "création", f"{u.email} ({u.role})")
    db.commit()
    return u


@router.patch("/users/{uid}", response_model=UserOut)
def modifier(uid: int, body: UserPatch, admin: User = Depends(require()), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")
    data = body.model_dump(exclude_unset=True)
    role, actif = data.get("role", u.role), data.get("actif", u.actif)
    if u.id == admin.id and (role != "Administrateur" or not actif):
        raise HTTPException(422, "Vous ne pouvez ni désactiver votre compte ni retirer vos droits d'administrateur")
    _client_ok(db, role, data.get("client_id", u.client_id))
    if role != "Client":
        data["client_id"] = None
    for k, v in data.items():
        setattr(u, k, v)
    audit(db, admin, "utilisateur", u.id, "modification", ", ".join(f"{k}={v}" for k, v in data.items()))
    db.commit()
    return u


@router.post("/users/{uid}/password", status_code=204)
def reinitialiser(uid: int, body: PasswordIn, admin: User = Depends(require()), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")
    u.pwd = hash_pwd(body.password)
    audit(db, admin, "utilisateur", u.id, "réinitialisation du mot de passe", u.email)
    db.commit()
    return Response(status_code=204)
