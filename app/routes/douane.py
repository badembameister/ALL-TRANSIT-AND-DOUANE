from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..audit import audit
from ..customs import compute, controls
from ..db import get_db
from ..deps import dossier_for, get_params
from ..gateway import gateway
from ..models import DeclMessage, Declaration, Dossier, User
from ..schemas import DeclOut, MessageIn
from ..security import W_DOUANE, require

router = APIRouter(prefix="/dossiers/{did}/declaration", tags=["Douane"])
REPONSES = {"Transmise": {"Acceptée", "Contrôle", "Rejetée"}, "Acceptée": {"Bon à enlever"}, "Contrôle": {"Bon à enlever"}}


def _decl(d: Dossier) -> Declaration:
    if not d.declaration:
        raise HTTPException(404, "Aucune déclaration en douane pour ce dossier")
    return d.declaration


def _msg(x: Declaration, sens: str, texte: str) -> None:
    x.messages.append(DeclMessage(sens=sens, texte=texte))


@router.post("", response_model=DeclOut, status_code=201)
def generer(d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOUANE)), db: Session = Depends(get_db)):
    if d.declaration:
        raise HTTPException(409, "Ce dossier a déjà une déclaration")
    d.declaration = Declaration(ref=f"DUM-{date.today().year}-{d.id:04d}")
    audit(db, u, "declaration", d.id, "projet généré")
    db.commit()
    return d.declaration


@router.get("", response_model=DeclOut)
def lire(d: Dossier = Depends(dossier_for)):
    return _decl(d)


@router.get("/calcul")
def calcul(d: Dossier = Depends(dossier_for), db: Session = Depends(get_db)):
    return {"liquidation": compute(d, get_params(db)), "controles": controls(d, {x.type for x in d.documents})}


@router.post("/transmettre", response_model=DeclOut)
def transmettre(d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOUANE)), db: Session = Depends(get_db)):
    x = _decl(d)
    if x.statut != "Brouillon":
        raise HTTPException(409, f"Transmission impossible : la déclaration est « {x.statut} »")
    bloquants = [c["controle"] for c in controls(d, {y.type for y in d.documents}) if not c["conforme"]]
    if bloquants:
        raise HTTPException(422, {"message": "Contrôles de cohérence non satisfaits", "bloquants": bloquants})
    ref = gateway.submit(x.ref, {"dossier": d.num, "liquidation": str(compute(d, get_params(db))["total"])})
    x.statut = "Transmise"
    _msg(x, "envoi", f"Déclaration transmise au système douanier (réf. {ref})")
    audit(db, u, "declaration", d.id, "transmission", ref)
    db.commit()
    return x


@router.post("/messages", response_model=DeclOut)
def message_douane(body: MessageIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOUANE)),
                   db: Session = Depends(get_db)):
    """Enregistre une réponse du système douanier (point d'entrée de la future passerelle)."""
    x = _decl(d)
    if body.statut not in REPONSES.get(x.statut, set()):
        raise HTTPException(409, f"Réponse « {body.statut} » impossible quand la déclaration est « {x.statut} »")
    audit(db, u, "declaration", d.id, "message douane", f"{x.statut} -> {body.statut}")
    x.statut = body.statut
    _msg(x, "réception", body.texte or f"Déclaration : {body.statut}")
    db.commit()
    return x


@router.post("/rouvrir", response_model=DeclOut)
def rouvrir(d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOUANE)), db: Session = Depends(get_db)):
    x = _decl(d)
    if x.statut != "Rejetée":
        raise HTTPException(409, "Seule une déclaration rejetée peut être rouverte")
    x.statut = "Brouillon"
    _msg(x, "interne", "Déclaration rouverte pour correction")
    audit(db, u, "declaration", d.id, "réouverture")
    db.commit()
    return x
