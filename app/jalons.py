"""Étapes opérationnelles d'un dossier, avec dates prévisionnelles et réelles (cahier des charges, point 4).
La date réelle vient des événements enregistrés dans l'application quand c'est possible ; sinon elle est saisie."""
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Audit, Conteneur, Dossier, Mission

TRANSIT_TYPES = {"Transit national", "Transit international", "T1/T2"}
ETAPES = [
    ("ouverture", "Ouverture du dossier", None),
    ("arrivee", "Arrivée des marchandises", None),
    ("depot", "Dépôt de la déclaration en douane", None),
    ("bae", "Bon à enlever", None),
    ("transit_depart", "Départ en transit", TRANSIT_TYPES),
    ("transit_apure", "Apurement du transit", TRANSIT_TYPES),
    ("enlevement", "Enlèvement", None),
    ("livraison", "Livraison", None),
    ("facture", "Facturation", None),
    ("cloture", "Clôture", None),
]
CLES = {k for k, _, _ in ETAPES}


def _audit_date(db: Session, d: Dossier, entite: str, action: str, fin: str = "") -> Optional[date]:
    st = select(Audit.ts).where(Audit.entite == entite, Audit.entite_id == d.id, Audit.action == action)
    if fin:
        st = st.where(Audit.detail.like(f"%{fin}"))
    ts = db.scalars(st.order_by(Audit.id)).first()
    return ts.date() if ts else None


def automatiques(db: Session, d: Dossier) -> dict[str, Optional[date]]:
    cts = db.scalars(select(Conteneur.arrivee).where(Conteneur.dossier_id == d.id, Conteneur.arrivee.is_not(None))).all()
    ms = db.scalars(select(Mission).where(Mission.dossier_id == d.id, Mission.statut == "Livrée")).all()
    debut = [m.debut.date() for m in ms if m.type == "Enlèvement" and m.debut]
    fin = [m.fin.date() for m in ms if m.type == "Livraison" and m.fin]
    t = d.transit
    return {
        "ouverture": d.created_at.date() if d.created_at else None,
        "arrivee": min(cts) if cts else None,
        "depot": _audit_date(db, d, "declaration", "transmission"),
        "bae": _audit_date(db, d, "declaration", "message douane", "-> Bon à enlever"),
        "transit_depart": t.depart if t else None,
        "transit_apure": t.apurement if t else None,
        "enlevement": min(debut) if debut else None,
        "livraison": max(fin) if fin else None,
        "facture": d.facture.date_emission if d.facture else None,
        "cloture": _audit_date(db, d, "dossier", "statut", "-> Clôturé"),
    }


def jalons(db: Session, d: Dossier) -> list[dict]:
    saisis, auto, today = d.jalons or {}, automatiques(db, d), date.today()
    out = []
    for cle, libelle, types in ETAPES:
        if types and d.type not in types:
            continue
        manuel = saisis.get(cle, {})
        prevue = date.fromisoformat(manuel["prevue"]) if manuel.get("prevue") else None
        reelle = auto.get(cle) or (date.fromisoformat(manuel["reelle"]) if manuel.get("reelle") else None)
        retard = bool(prevue and ((reelle and reelle > prevue) or (not reelle and prevue < today)))
        out.append({"cle": cle, "libelle": libelle, "prevue": prevue, "reelle": reelle,
                    "automatique": bool(auto.get(cle)), "retard": retard,
                    "ecart_jours": (reelle - prevue).days if (prevue and reelle) else None})
    return out
