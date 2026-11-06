from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import get_params
from ..models import Audit, Dossier, Facture, Param, User
from ..schemas import ParamsIn
from ..security import STAFF, require

router = APIRouter(tags=["Paramétrage et pilotage"])


@router.get("/params")
def lire_params(_: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    return get_params(db)


@router.put("/params")
def maj_params(body: ParamsIn, u: User = Depends(require()), db: Session = Depends(get_db)):
    value = body.model_dump()
    p = db.get(Param, "douane")
    if p:
        p.value = value
    else:
        db.add(Param(key="douane", value=value))
    audit(db, u, "parametres", 0, "mise à jour")
    db.commit()
    return value


@router.get("/audit")
def journal(limit: int = 200, _: User = Depends(require("Direction")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Audit).order_by(Audit.id.desc()).limit(min(limit, 1000))).all()
    return [{"ts": a.ts, "utilisateur": a.utilisateur, "entite": a.entite, "entite_id": a.entite_id,
             "action": a.action, "detail": a.detail} for a in rows]


@router.get("/dashboard")
def dashboard(_: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    rates = get_params(db)["rates"]
    dossiers = db.scalars(select(Dossier)).all()
    factures = db.scalars(select(Facture)).all()
    en_retard = [d for d in dossiers if d.transit and d.transit.en_retard]
    fact_retard = [f for f in factures if f.statut == "En retard"]
    rate = lambda dev: Decimal(str(rates.get(dev, 1)))  # noqa: E731
    ca: dict[str, Decimal] = {}
    for f in factures:
        ca[f.dossier.client.nom] = ca.get(f.dossier.client.nom, Decimal(0)) + f.total * rate(f.devise)
    alertes = [f"Transit {d.num} non apuré, délai dépassé" for d in en_retard]
    alertes += [f"Facture {f.num} en retard" for f in fact_retard]
    alertes += [f"Dossier {d.num} bloqué" for d in dossiers if d.statut == "Bloqué"]
    alertes += [f"Documents manquants sur {d.num} ({d.completude} % complet)" for d in dossiers if d.completude < 100]
    return {
        "dossiers_ouverts": sum(d.statut not in {"Livré", "Clôturé"} for d in dossiers),
        "dossiers_bloques": sum(d.statut == "Bloqué" for d in dossiers),
        "transits_en_cours": sum(bool(d.transit and d.transit.statut in {"En circulation", "Contrôlée", "Arrivée à destination"}) for d in dossiers),
        "transits_en_retard": len(en_retard),
        "taux_dossiers_complets": round(100 * sum(d.completude == 100 for d in dossiers) / (len(dossiers) or 1)),
        "creances_base": float(sum((f.solde * rate(f.devise) for f in factures), Decimal(0))),
        "factures_en_retard": len(fact_retard),
        "ca_par_client": [{"client": k, "montant_base": float(v)} for k, v in ca.items()],
        "alertes": alertes,
    }
