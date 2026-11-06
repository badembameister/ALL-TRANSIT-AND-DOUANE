import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..customs import compute
from ..db import get_db
from ..deps import dossier_for, get_params
from ..models import Dossier, Facture, FactureLigne, Paiement, User
from ..schemas import FactureIn, FactureOut, PaiementIn
from ..security import W_FACT, require

router = APIRouter(tags=["Facturation"])
VOIR = ("Comptable", "Direction")
CENT = Decimal("0.01")


@router.post("/dossiers/{did}/facture", response_model=FactureOut, status_code=201)
def generer(body: FactureIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_FACT)),
            db: Session = Depends(get_db)):
    if d.facture:
        raise HTTPException(409, "Ce dossier a déjà une facture")
    p = get_params(db)
    rate = Decimal(str(p["rates"].get(d.client.devise, 1)))
    lignes = [(x.libelle, x.montant) for x in body.lignes]
    if body.refacturer_debours:
        total = compute(d, p)["total"]
        if total > 0:
            lignes.append(("Droits et taxes avancés (débours)", total))
    if not lignes:
        raise HTTPException(422, "Aucune ligne à facturer")
    f = Facture(dossier_id=d.id, client_id=d.client_id, devise=d.client.devise,
                echeance=date.today() + timedelta(days=d.client.delai_paiement),
                lignes=[FactureLigne(libelle=lib, montant=(m / rate).quantize(CENT)) for lib, m in lignes])
    db.add(f)
    db.flush()
    f.num = f"FA-{date.today().year}-{f.id:04d}"
    audit(db, u, "facture", d.id, "génération", f.num)
    db.commit()
    return f


@router.get("/dossiers/{did}/facture", response_model=FactureOut)
def du_dossier(d: Dossier = Depends(dossier_for), _: User = Depends(require(*VOIR, "Responsable transit"))):
    if not d.facture:
        raise HTTPException(404, "Aucune facture pour ce dossier")
    return d.facture


@router.get("/factures", response_model=list[FactureOut])
def lister(_: User = Depends(require(*VOIR)), db: Session = Depends(get_db)):
    return db.scalars(select(Facture).order_by(Facture.id.desc())).all()


@router.get("/factures/export.csv")
def export_csv(_: User = Depends(require(*VOIR)), db: Session = Depends(get_db)):
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Facture", "Date", "Client", "Devise", "Total", "Réglé", "Solde", "Statut"])
    for f in db.scalars(select(Facture).order_by(Facture.id)):
        w.writerow([f.num, f.date_emission, f.dossier.client.nom, f.devise, f.total, f.paye, f.solde, f.statut])
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="factures.csv"'})


def _facture(db: Session, fid: int) -> Facture:
    f = db.get(Facture, fid)
    if not f:
        raise HTTPException(404, "Facture introuvable")
    return f


@router.post("/factures/{fid}/paiements", response_model=FactureOut, status_code=201)
def payer(fid: int, body: PaiementIn, u: User = Depends(require(*W_FACT)), db: Session = Depends(get_db)):
    f = _facture(db, fid)
    if body.montant > f.solde:
        raise HTTPException(422, f"Le règlement dépasse le solde ({f.solde} {f.devise})")
    f.paiements.append(Paiement(montant=body.montant))
    audit(db, u, "facture", f.dossier_id, "règlement", f"{body.montant} {f.devise} sur {f.num}")
    db.commit()
    return f


@router.post("/factures/{fid}/relance", response_model=FactureOut)
def relancer(fid: int, u: User = Depends(require(*W_FACT)), db: Session = Depends(get_db)):
    f = _facture(db, fid)
    if f.statut == "Payée":
        raise HTTPException(409, "Facture déjà soldée")
    f.relances += 1
    audit(db, u, "facture", f.dossier_id, "relance", f"n°{f.relances} pour {f.num}")
    db.commit()
    return f
