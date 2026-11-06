from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import dossier_for
from ..models import Dossier, Transit, User
from ..schemas import IncidentIn, TransitIn, TransitionIn, TransitOut
from ..security import W_TRANSIT, require

router = APIRouter(prefix="/dossiers/{did}/transit", tags=["Transit"])
ETAPES = ["En préparation", "Déposée", "Acceptée", "En circulation", "Contrôlée", "Arrivée à destination", "Apurée"]


def _transit(d: Dossier) -> Transit:
    if not d.transit:
        raise HTTPException(404, "Aucune déclaration de transit pour ce dossier")
    return d.transit


def autorisees(statut: str) -> set[str]:
    if statut == "Rejetée":
        return {"En préparation"}
    i = ETAPES.index(statut)
    nxt = {ETAPES[i + 1]} if i < len(ETAPES) - 1 else set()
    if statut == "En circulation":
        nxt.add("Arrivée à destination")  # arrivée sans contrôle
    if statut != "Apurée":
        nxt.add("Rejetée")
    return nxt


@router.post("", response_model=TransitOut, status_code=201)
def creer(body: TransitIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_TRANSIT)),
          db: Session = Depends(get_db)):
    if d.transit:
        raise HTTPException(409, "Ce dossier a déjà une déclaration de transit")
    d.transit = Transit(**body.model_dump())
    audit(db, u, "transit", d.id, "création")
    db.commit()
    return d.transit


@router.get("", response_model=TransitOut)
def lire(d: Dossier = Depends(dossier_for)):
    return _transit(d)


@router.post("/transition", response_model=TransitOut)
def transition(body: TransitionIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_TRANSIT)),
               db: Session = Depends(get_db)):
    t = _transit(d)
    ok = autorisees(t.statut)
    if body.to not in ok:
        raise HTTPException(409, f"Passage impossible depuis « {t.statut} ». Étapes permises : {', '.join(sorted(ok)) or 'aucune'}")
    audit(db, u, "transit", d.id, "statut", f"{t.statut} -> {body.to}")
    t.statut = body.to
    if body.to == "En circulation":
        t.depart = date.today()
    db.commit()
    return t


@router.post("/incidents", response_model=TransitOut, status_code=201)
def incident(body: IncidentIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_TRANSIT)),
             db: Session = Depends(get_db)):
    t = _transit(d)
    t.incidents = [{"date": date.today().isoformat(), **body.model_dump()}, *t.incidents]
    audit(db, u, "transit", d.id, "incident", body.type)
    db.commit()
    return t
