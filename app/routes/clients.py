from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..models import Client, User
from ..schemas import ClientIn, ClientOut
from ..security import STAFF, W_CLIENT, require

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.get("", response_model=list[ClientOut])
def lister(_: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    return db.scalars(select(Client).order_by(Client.nom)).all()


@router.post("", response_model=ClientOut, status_code=201)
def creer(body: ClientIn, u: User = Depends(require(*W_CLIENT)), db: Session = Depends(get_db)):
    c = Client(**body.model_dump())
    db.add(c)
    db.flush()
    c.code = f"C{c.id:04d}"
    audit(db, u, "client", c.id, "création", c.nom)
    db.commit()
    return c


@router.put("/{cid}", response_model=ClientOut)
def modifier(cid: int, body: ClientIn, u: User = Depends(require(*W_CLIENT)), db: Session = Depends(get_db)):
    c = db.get(Client, cid)
    if not c:
        raise HTTPException(404, "Client introuvable")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, u, "client", c.id, "modification")
    db.commit()
    return c
