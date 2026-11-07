"""Facturation et finance (cahier des charges, point 9) : devis, factures multi-devises, avances, avoirs,
règlements partiels, relances, balance âgée et exports comptables."""
import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..fmt import milliers
from ..audit import audit
from ..customs import compute
from ..db import get_db
from ..deps import dossier_for, get_params
from ..models import Avance, Avoir, Devis, Dossier, Facture, FactureLigne, Paiement, User
from ..schemas import (AvanceIn, AvanceOut, AvoirIn, DevisIn, DevisOut, DevisStatutIn, FactureIn, FactureOut,
                       FacturerDevisIn, PaiementIn)
from ..security import W_FACT, require
from .admin import get_societe

router = APIRouter(tags=["Facturation"])
VOIR = ("Comptable", "Direction", "Commercial", "Responsable transit")
W_DEVIS = ("Comptable", "Commercial", "Responsable transit")
CENT = Decimal("0.01")
DEBOURS = "Droits et taxes avancés (débours)"
DEVIS_SUIVANT = {"Brouillon": {"Envoyé", "Accepté", "Refusé"}, "Envoyé": {"Accepté", "Refusé"}, "Refusé": {"Envoyé"}}
PREMIERE_RELANCE, INTERVALLE_RELANCE = 1, 15  # jours après l'échéance, puis entre deux relances


def _rate(db: Session, devise: str) -> Decimal:
    return Decimal(str(get_params(db)["rates"].get(devise, 1)))


def _vers(montant_base: Decimal, rate: Decimal) -> Decimal:
    return (Decimal(montant_base) / rate).quantize(CENT)


def _facture(db: Session, fid: int) -> Facture:
    f = db.get(Facture, fid)
    if not f:
        raise HTTPException(404, "Facture introuvable")
    return f


def _devis(db: Session, did: int) -> Devis:
    x = db.get(Devis, did)
    if not x:
        raise HTTPException(404, "Devis introuvable")
    return x


def _creer_facture(db: Session, u: User, d: Dossier, lignes: list[tuple[str, Decimal]], debours: bool,
                   devis: Optional[Devis] = None) -> Facture:
    """lignes : montants déjà exprimés dans la devise du client."""
    if d.facture:
        raise HTTPException(409, "Ce dossier a déjà une facture")
    rate = _rate(db, d.client.devise)
    if debours:
        total = compute(d, get_params(db))["total"]
        if total > 0:
            lignes.append((DEBOURS, _vers(total, rate)))
    if not lignes:
        raise HTTPException(422, "Aucune ligne à facturer")
    f = Facture(dossier_id=d.id, client_id=d.client_id, devise=d.client.devise, devis_id=devis.id if devis else None,
                echeance=date.today() + timedelta(days=d.client.delai_paiement),
                lignes=[FactureLigne(libelle=lib, montant=m) for lib, m in lignes])
    db.add(f)
    db.flush()
    f.num = f"FA-{date.today().year}-{f.id:04d}"
    # Imputation des avances reçues sur le dossier
    for a in db.scalars(select(Avance).where(Avance.dossier_id == d.id, Avance.facture_id.is_(None))).all():
        part = min(a.montant if a.devise == f.devise else _vers(a.montant * _rate(db, a.devise), rate), f.solde)
        if part > 0:
            f.paiements.append(Paiement(montant=part, mode="Avance", reference=a.reference or f"Avance du {a.date:%d/%m/%Y}"))
        a.facture_id = f.id
    audit(db, u, "facture", d.id, "génération", f.num + (f" (devis {devis.num})" if devis else ""))
    return f


# ---------- Factures ----------

@router.post("/dossiers/{did}/facture", response_model=FactureOut, status_code=201)
def generer(body: FactureIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_FACT)),
            db: Session = Depends(get_db)):
    rate = _rate(db, d.client.devise)
    f = _creer_facture(db, u, d, [(x.libelle, _vers(x.montant, rate)) for x in body.lignes], body.refacturer_debours)
    db.commit()
    return f


@router.get("/dossiers/{did}/facture", response_model=FactureOut)
def du_dossier(d: Dossier = Depends(dossier_for), _: User = Depends(require(*VOIR))):
    if not d.facture:
        raise HTTPException(404, "Aucune facture pour ce dossier")
    return d.facture


def _filtre(db: Session, statut: str = "", client_id: int = 0, du: Optional[date] = None, au: Optional[date] = None,
            q: str = "") -> list[Facture]:
    st = select(Facture).order_by(Facture.id.desc())
    if client_id:
        st = st.where(Facture.client_id == client_id)
    if du:
        st = st.where(Facture.date_emission >= du)
    if au:
        st = st.where(Facture.date_emission <= au)
    rows = db.scalars(st).all()
    if statut == "ouvertes":
        rows = [f for f in rows if f.solde > 0]
    elif statut:
        rows = [f for f in rows if f.statut == statut]
    if q:
        ql = q.lower()
        rows = [f for f in rows if ql in f"{f.num} {f.client_nom} {f.dossier_num}".lower()]
    return rows


@router.get("/factures", response_model=list[FactureOut])
def lister(statut: str = "", client_id: int = 0, du: Optional[date] = None, au: Optional[date] = None, q: str = "",
           _: User = Depends(require(*VOIR)), db: Session = Depends(get_db)):
    return _filtre(db, statut, client_id, du, au, q)


@router.get("/factures/resume")
def resume(_: User = Depends(require(*VOIR)), db: Session = Depends(get_db)):
    p, today = get_params(db), date.today()
    debut_mois = today.replace(day=1)
    rate = lambda dev: Decimal(str(p["rates"].get(dev, 1)))  # noqa: E731
    fs = db.scalars(select(Facture)).all()
    tranches = {"non_echu": Decimal(0), "1_30": Decimal(0), "31_60": Decimal(0), "61_90": Decimal(0), "plus_90": Decimal(0)}
    for f in fs:
        if f.solde <= 0:
            continue
        j, v = f.jours_retard, f.solde * rate(f.devise)
        k = "non_echu" if j == 0 else "1_30" if j <= 30 else "31_60" if j <= 60 else "61_90" if j <= 90 else "plus_90"
        tranches[k] += v
    devis = db.scalars(select(Devis).where(Devis.statut.in_(["Brouillon", "Envoyé"]))).all()
    avances = db.scalars(select(Avance).where(Avance.facture_id.is_(None))).all()
    return {
        "devise_base": p["base"],
        "facture_mois": float(sum((f.total * rate(f.devise) for f in fs if f.date_emission >= debut_mois), Decimal(0))),
        # Encaissements du mois : règlements, plus avances à leur date de réception (l'imputation n'est pas un encaissement)
        "encaisse_mois": float(sum((x.montant * rate(f.devise) for f in fs for x in f.paiements
                                    if x.date >= debut_mois and x.mode != "Avance"), Decimal(0))
                               + sum((a.montant * rate(a.devise) for a in db.scalars(select(Avance).where(Avance.date >= debut_mois))),
                                     Decimal(0))),
        "creances": float(sum(tranches.values())),
        "en_retard": sum(f.jours_retard > 0 for f in fs),
        "a_relancer": len(_a_relancer(fs)),
        "balance_agee": {k: float(v) for k, v in tranches.items()},
        "devis_en_attente": len([x for x in devis if not x.expire]),
        "devis_montant": float(sum((x.total * rate(x.devise) for x in devis if not x.expire), Decimal(0))),
        "avances_non_imputees": float(sum((a.montant * rate(a.devise) for a in avances), Decimal(0))),
    }


@router.get("/factures/{fid:int}", response_model=FactureOut)
def lire(fid: int, _: User = Depends(require(*VOIR)), db: Session = Depends(get_db)):
    return _facture(db, fid)


@router.post("/factures/{fid}/paiements", response_model=FactureOut, status_code=201)
def payer(fid: int, body: PaiementIn, u: User = Depends(require(*W_FACT)), db: Session = Depends(get_db)):
    f = _facture(db, fid)
    if body.montant > f.solde:
        raise HTTPException(422, f"Le règlement dépasse le solde ({f.solde} {f.devise})")
    f.paiements.append(Paiement(montant=body.montant, mode=body.mode, reference=body.reference,
                                date=body.date or date.today()))
    audit(db, u, "facture", f.dossier_id, "règlement", f"{body.montant} {f.devise} ({body.mode}) sur {f.num}")
    db.commit()
    return f


@router.post("/factures/{fid}/avoirs", response_model=FactureOut, status_code=201)
def avoir(fid: int, body: AvoirIn, u: User = Depends(require(*W_FACT)), db: Session = Depends(get_db)):
    f = _facture(db, fid)
    if body.montant > f.solde:
        raise HTTPException(422, f"L'avoir dépasse le solde restant dû ({f.solde} {f.devise})")
    a = Avoir(facture_id=f.id, montant=body.montant, motif=body.motif)
    f.avoirs.append(a)
    db.flush()
    a.num = f"AV-{date.today().year}-{a.id:04d}"
    audit(db, u, "facture", f.dossier_id, "avoir", f"{a.num} : {body.montant} {f.devise} sur {f.num} ({body.motif})")
    db.commit()
    return f


# ---------- Relances ----------

def _niveau(n: int) -> str:
    return ("Rappel amiable", "Deuxième relance", "Mise en demeure")[min(n, 2)]


def _a_relancer(fs: list[Facture]) -> list[Facture]:
    today = date.today()
    return [f for f in fs if f.solde > 0 and f.jours_retard >= PREMIERE_RELANCE
            and (not f.derniere_relance or (today - f.derniere_relance).days >= INTERVALLE_RELANCE)]


def _lettre(f: Facture, societe: dict) -> str:
    n = _niveau(f.relances)
    corps = {
        "Rappel amiable": "Sauf erreur de notre part, le règlement de la facture ci-dessous ne nous est pas parvenu. "
                          "Nous vous remercions de bien vouloir procéder à son paiement dans les meilleurs délais.",
        "Deuxième relance": "Malgré notre précédent rappel, la facture ci-dessous reste impayée. "
                            "Nous vous prions de régulariser la situation sous huit jours.",
        "Mise en demeure": "Malgré nos relances, la facture ci-dessous demeure impayée. Nous vous mettons en demeure "
                           "de la régler sous huit jours, faute de quoi nous engagerons les démarches de recouvrement.",
    }[n]
    return (f"Objet : {n} – facture {f.num}\n\nMadame, Monsieur,\n\n{corps}\n\nFacture {f.num} du {f.date_emission:%d/%m/%Y}, "
            f"échéance {f.echeance:%d/%m/%Y} ({f.jours_retard} jours de retard), dossier {f.dossier_num}.\n"
            f"Montant restant dû : {milliers(f.solde, 2)} {f.devise}.\n\nVeuillez agréer nos salutations distinguées.\n"
            f"{societe['signature']} – {societe['nom']}")


def _relancer(db: Session, u: User, f: Facture) -> dict:
    niveau = _niveau(f.relances)
    lettre = _lettre(f, get_societe(db))
    f.relances += 1
    f.derniere_relance = date.today()
    audit(db, u, "facture", f.dossier_id, "relance", f"n°{f.relances} ({niveau}) pour {f.num}")
    return {"facture_id": f.id, "num": f.num, "client": f.client_nom, "niveau": niveau, "lettre": lettre}


@router.get("/factures-relances")
def relances_dues(_: User = Depends(require(*VOIR)), db: Session = Depends(get_db)):
    """Factures à relancer : échues depuis au moins 1 jour, sans relance depuis 15 jours."""
    societe = get_societe(db)
    return [{"facture_id": f.id, "num": f.num, "client": f.client_nom, "solde": float(f.solde), "devise": f.devise,
             "jours_retard": f.jours_retard, "relances": f.relances, "derniere_relance": f.derniere_relance,
             "niveau": _niveau(f.relances), "lettre": _lettre(f, societe)}
            for f in _a_relancer(db.scalars(select(Facture).order_by(Facture.echeance)).all())]


@router.post("/factures-relances")
def relancer_tout(u: User = Depends(require(*W_FACT)), db: Session = Depends(get_db)):
    faites = [_relancer(db, u, f) for f in _a_relancer(db.scalars(select(Facture)).all())]
    db.commit()
    return faites


@router.post("/factures/{fid}/relance")
def relancer(fid: int, u: User = Depends(require(*W_FACT)), db: Session = Depends(get_db)):
    f = _facture(db, fid)
    if f.solde <= 0:
        raise HTTPException(409, "Facture déjà soldée")
    r = _relancer(db, u, f)
    db.commit()
    return FactureOut.model_validate(f).model_dump() | {"lettre": r["lettre"], "niveau": r["niveau"]}


# ---------- Avances ----------

@router.get("/dossiers/{did}/avances", response_model=list[AvanceOut])
def avances(d: Dossier = Depends(dossier_for), _: User = Depends(require(*VOIR)), db: Session = Depends(get_db)):
    return db.scalars(select(Avance).where(Avance.dossier_id == d.id).order_by(Avance.id)).all()


@router.post("/dossiers/{did}/avances", response_model=AvanceOut, status_code=201)
def avance(body: AvanceIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_FACT)),
           db: Session = Depends(get_db)):
    if d.facture:
        raise HTTPException(409, f"Dossier déjà facturé : enregistrez un règlement sur {d.facture.num}")
    a = Avance(dossier_id=d.id, montant=body.montant, devise=d.client.devise, mode=body.mode, reference=body.reference,
               date=body.date or date.today())
    db.add(a)
    audit(db, u, "facture", d.id, "avance", f"{body.montant} {d.client.devise} ({body.mode})")
    db.commit()
    return a


# ---------- Devis ----------

@router.post("/dossiers/{did}/devis", response_model=DevisOut, status_code=201)
def creer_devis(body: DevisIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DEVIS)),
                db: Session = Depends(get_db)):
    rate = _rate(db, d.client.devise)
    x = Devis(dossier_id=d.id, client_id=d.client_id, devise=d.client.devise, conditions=body.conditions, cree_par=u.email,
              validite=date.today() + timedelta(days=body.validite_jours),
              lignes=[{"libelle": ln.libelle, "montant": float(_vers(ln.montant, rate))} for ln in body.lignes])
    db.add(x)
    db.flush()
    x.num = f"DV-{date.today().year}-{x.id:04d}"
    audit(db, u, "facture", d.id, "devis", x.num)
    db.commit()
    return x


@router.get("/dossiers/{did}/devis", response_model=list[DevisOut])
def devis_dossier(d: Dossier = Depends(dossier_for), _: User = Depends(require(*VOIR)), db: Session = Depends(get_db)):
    return db.scalars(select(Devis).where(Devis.dossier_id == d.id).order_by(Devis.id.desc())).all()


@router.get("/devis", response_model=list[DevisOut])
def lister_devis(statut: str = "", _: User = Depends(require(*VOIR)), db: Session = Depends(get_db)):
    rows = db.scalars(select(Devis).order_by(Devis.id.desc())).all()
    return [x for x in rows if x.statut == statut] if statut else rows


@router.post("/devis/{xid}/statut", response_model=DevisOut)
def statut_devis(xid: int, body: DevisStatutIn, u: User = Depends(require(*W_DEVIS)), db: Session = Depends(get_db)):
    x = _devis(db, xid)
    if body.statut not in DEVIS_SUIVANT.get(x.statut, set()):
        raise HTTPException(409, f"Devis « {x.statut} » : passage à « {body.statut} » impossible")
    if body.statut == "Accepté" and x.expire:
        raise HTTPException(409, f"Devis expiré le {x.validite:%d/%m/%Y} : établissez un nouveau devis")
    audit(db, u, "facture", x.dossier_id, "devis", f"{x.num} : {x.statut} -> {body.statut}")
    x.statut = body.statut
    db.commit()
    return x


@router.post("/devis/{xid}/facturer", response_model=FactureOut, status_code=201)
def facturer_devis(xid: int, body: FacturerDevisIn, u: User = Depends(require(*W_FACT)), db: Session = Depends(get_db)):
    x = _devis(db, xid)
    if x.statut != "Accepté":
        raise HTTPException(409, "Seul un devis accepté peut être facturé")
    if x.devise != x.dossier.client.devise:
        raise HTTPException(409, "La devise du client a changé depuis le devis : établissez un nouveau devis")
    f = _creer_facture(db, u, x.dossier, [(ln["libelle"], Decimal(str(ln["montant"]))) for ln in x.lignes],
                       body.refacturer_debours, devis=x)
    x.statut = "Facturé"
    db.commit()
    return f


# ---------- Exports comptables ----------

def _csv(nom: str, entete: list[str], lignes) -> Response:
    out = io.StringIO()
    out.write("﻿")  # BOM : accents corrects à l'ouverture dans Excel
    w = csv.writer(out, delimiter=";")
    w.writerow(entete)
    for ln in lignes:
        w.writerow([str(v).replace(".", ",") if isinstance(v, (Decimal, float)) else v for v in ln])
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


@router.get("/factures/export.csv")
def export_csv(du: Optional[date] = None, au: Optional[date] = None, _: User = Depends(require(*VOIR)),
               db: Session = Depends(get_db)):
    fs = sorted(_filtre(db, du=du, au=au), key=lambda f: f.id)
    return _csv("factures.csv", ["Facture", "Date", "Échéance", "Client", "Code client", "NIF", "Dossier", "Devise", "Total",
                                 "Dont débours", "Réglé", "Avoirs", "Solde", "Statut"],
                [[f.num, f.date_emission, f.echeance, f.client_nom, f.client.code, f.client.nif, f.dossier_num, f.devise,
                  f.total, sum((x.montant for x in f.lignes if x.libelle == DEBOURS), Decimal(0)), f.paye, f.total_avoirs,
                  f.solde, f.statut] for f in fs])


@router.get("/factures/export-ventes.csv")
def export_ventes(du: Optional[date] = None, au: Optional[date] = None, _: User = Depends(require(*VOIR)),
                  db: Session = Depends(get_db)):
    """Journal des ventes : une ligne par prestation facturée, avec la contre-valeur en devise de base."""
    rows = []
    for f in sorted(_filtre(db, du=du, au=au), key=lambda f: f.id):
        r = _rate(db, f.devise)
        rows += [[f.date_emission, f.num, f.client.code, f.client_nom, x.libelle, f.devise, x.montant, (x.montant * r).quantize(CENT)]
                 for x in f.lignes]
        rows += [[a.date, a.num, f.client.code, f.client_nom, f"Avoir sur {f.num} : {a.motif}", f.devise, -a.montant,
                  (-a.montant * r).quantize(CENT)] for a in f.avoirs]
    return _csv("journal-ventes.csv", ["Date", "Pièce", "Code client", "Client", "Libellé", "Devise", "Montant",
                                       f"Montant {get_params(db)['base']}"], rows)


@router.get("/factures/export-reglements.csv")
def export_reglements(du: Optional[date] = None, au: Optional[date] = None, _: User = Depends(require(*VOIR)),
                      db: Session = Depends(get_db)):
    rows = []
    for f in db.scalars(select(Facture).order_by(Facture.id)).all():
        r = _rate(db, f.devise)
        rows += [[p.date, f.num, f.client.code, f.client_nom, p.mode, p.reference, f.devise, p.montant, (p.montant * r).quantize(CENT)]
                 for p in f.paiements if (not du or p.date >= du) and (not au or p.date <= au)]
    return _csv("reglements.csv", ["Date", "Facture", "Code client", "Client", "Mode", "Référence", "Devise", "Montant",
                                   f"Montant {get_params(db)['base']}"], sorted(rows, key=lambda x: x[0]))


