"""Portail client (cahier des charges, points 2 et 16) : accueil, notifications et factures du client connecté.
Tout est filtré sur le client rattaché au compte ; aucune donnée interne (coûts, marges, employés) n'en sort."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..customs import DOC_TYPES, required_docs
from ..db import get_db
from ..jalons import jalons
from ..models import Audit, Dossier, Facture, Mission, User
from ..schemas import FactureOut
from ..security import require

router = APIRouter(prefix="/portail", tags=["Portail client"])
CLIENT = require("Client")
TERMINES = {"Livré", "Clôturé"}


def _client_id(u: User) -> int:
    if not u.client_id:
        raise HTTPException(403, "Compte client non rattaché à un client : contactez Alliance Transit")
    return u.client_id


def _dossiers(db: Session, u: User) -> list[Dossier]:
    return db.scalars(select(Dossier).where(Dossier.client_id == _client_id(u)).order_by(Dossier.id.desc())).all()


def _apres(detail: str) -> str:
    return detail.split("->")[-1].strip() if "->" in detail else ""


def _traduire(a: Audit, num: str) -> Optional[tuple[str, str]]:
    """Événement interne -> (niveau, message lisible par le client), ou None s'il ne le concerne pas."""
    e, act, cible = a.entite, a.action, _apres(a.detail)
    if e == "dossier":
        if act == "création":
            return "info", f"Dossier {num} ouvert"
        if act == "statut":
            return ("alerte" if cible == "Bloqué" else "ok" if cible in TERMINES else "info"), f"Dossier {num} : {cible.lower()}"
    elif e == "document" and act == "dépôt":
        lib = DOC_TYPES.get(a.detail.split(" ")[0], "Document")
        return "info", f"{num} : document ajouté ({lib})"
    elif e == "declaration":
        if act == "transmission":
            return "info", f"{num} : déclaration transmise à la douane"
        if act == "quittance":
            return "ok", f"{num} : droits et taxes de douane acquittés"
        if act == "message douane":
            return {"Acceptée": ("ok", f"{num} : déclaration acceptée par la douane"),
                    "Contrôle": ("info", f"{num} : contrôle douanier en cours"),
                    "Rejetée": ("alerte", f"{num} : déclaration à corriger, nous nous en occupons"),
                    "Bon à enlever": ("ok", f"{num} : bon à enlever obtenu, marchandises libérées")}.get(cible)
    elif e == "transit":
        if act == "création":
            return "info", f"{num} : déclaration de transit préparée"
        if act == "statut":
            return {"En circulation": ("info", f"{num} : marchandises en route (transit)"),
                    "Arrivée à destination": ("ok", f"{num} : arrivée au bureau de destination"),
                    "Apurée": ("ok", f"{num} : transit apuré, opération terminée"),
                    "Rejetée": ("alerte", f"{num} : déclaration de transit à corriger")}.get(cible)
        if act == "passage":
            return "info", f"{num} : passage au bureau de {a.detail}"
        if act == "incident":
            return "alerte", f"{num} : incident signalé en route ({a.detail.lower()})"
    elif e == "facture":
        if act == "génération":
            return "info", f"{num} : facture {a.detail.split(' ')[0]} émise"
        if act == "règlement":
            return "ok", f"{num} : règlement enregistré, merci"
        if act == "avoir":
            return "ok", f"{num} : avoir émis en votre faveur"
        if act == "relance":
            return "alerte", f"{num} : rappel de paiement"
        if act == "avance":
            return "ok", f"{num} : avance reçue, merci"
    elif e == "mission":
        if act == "création":
            return "info", f"{num} : transport planifié"
        if act == "statut" and cible == "En cours":
            return "info", f"{num} : transport en cours"
        if act == "livraison":
            return "ok", f"{num} : marchandises livrées"
        if act == "incident":
            return "alerte", f"{num} : incident de transport ({a.detail.lower()})"
    return None


def _notifications(db: Session, u: User, dossiers: list[Dossier], limite: int = 40) -> list[dict]:
    nums = {d.id: d.num for d in dossiers}
    if not nums:
        return []
    missions = {m.id: m.dossier_id for m in db.scalars(select(Mission).where(Mission.dossier_id.in_(nums))).all()}
    rows = db.scalars(select(Audit).where(or_(
        Audit.entite.in_(["dossier", "document", "declaration", "transit", "facture"]) & Audit.entite_id.in_(nums),
        (Audit.entite == "mission") & Audit.entite_id.in_(missions or [0]),
    )).order_by(Audit.id.desc()).limit(400)).all()
    out = []
    for a in rows:
        did = missions.get(a.entite_id) if a.entite == "mission" else a.entite_id
        t = _traduire(a, nums.get(did, ""))
        if t:
            out.append({"ts": a.ts, "niveau": t[0], "texte": t[1], "dossier_id": did,
                        "nouveau": bool(u.notifs_vues_le is None or a.ts > u.notifs_vues_le)})
        if len(out) >= limite:
            break
    return out


@router.get("/accueil")
def accueil(u: User = Depends(CLIENT), db: Session = Depends(get_db)):
    ds = _dossiers(db, u)
    en_cours = [d for d in ds if d.statut not in TERMINES]
    dossiers = []
    for d in en_cours:
        js = jalons(db, d)
        prochaine = next((j for j in js if not j["reelle"]), None)
        have = {x.type for x in d.documents}
        dossiers.append({"id": d.id, "num": d.num, "type": d.type, "ref": d.ref, "designation": d.designation, "statut": d.statut,
                         "completude": d.completude, "pieces_manquantes": [DOC_TYPES[k] for k in required_docs(d.type) if k not in have],
                         "douane": d.declaration_statut, "transit": d.transit_statut,
                         "etapes_faites": sum(1 for j in js if j["reelle"]), "etapes": len(js),
                         "prochaine_etape": {"libelle": prochaine["libelle"], "prevue": prochaine["prevue"]} if prochaine else None})
    ids = [d.id for d in ds]
    livraisons = db.scalars(select(Mission).where(Mission.dossier_id.in_(ids or [0]), Mission.statut.in_(["Planifiée", "En cours"]))
                            .order_by(Mission.date_prevue)).all()
    factures = [f for f in db.scalars(select(Facture).where(Facture.client_id == u.client_id)).all() if f.solde > 0]
    notifs = _notifications(db, u, ds)
    return {
        "dossiers": dossiers, "termines": len(ds) - len(en_cours),
        "livraisons": [{"num": m.num, "type": m.type, "date_prevue": m.date_prevue, "origine": m.origine, "destination": m.destination,
                        "statut": m.statut, "dossier_num": m.dossier_num, "dossier_id": m.dossier_id} for m in livraisons],
        "a_payer": [{"id": f.id, "num": f.num, "dossier_num": f.dossier_num, "echeance": f.echeance, "solde": float(f.solde),
                     "devise": f.devise, "jours_retard": f.jours_retard} for f in sorted(factures, key=lambda f: f.echeance)],
        "notifications": notifs[:15], "non_lues": sum(n["nouveau"] for n in notifs),
    }


@router.get("/notifications")
def notifications(u: User = Depends(CLIENT), db: Session = Depends(get_db)):
    return _notifications(db, u, _dossiers(db, u), limite=100)


@router.post("/notifications/vues", status_code=204)
def notifications_vues(u: User = Depends(CLIENT), db: Session = Depends(get_db)):
    u.notifs_vues_le = datetime.utcnow()
    db.commit()


@router.get("/factures", response_model=list[FactureOut])
def mes_factures(u: User = Depends(CLIENT), db: Session = Depends(get_db)):
    return db.scalars(select(Facture).where(Facture.client_id == _client_id(u)).order_by(Facture.id.desc())).all()


@router.get("/factures/{fid}", response_model=FactureOut)
def ma_facture(fid: int, u: User = Depends(CLIENT), db: Session = Depends(get_db)):
    f = db.get(Facture, fid)
    if not f or f.client_id != _client_id(u):
        raise HTTPException(404, "Facture introuvable")
    return f
