"""Module douane (cahier des charges, point 6) : projet de déclaration, liquidation, contrôles, transmission,
réponses du système douanier, quittance des droits et suivi des délais de dédouanement."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..customs import compute, controls
from ..db import get_db
from ..deps import dossier_for, get_params
from ..gateway import gateway
from ..models import Cout, DeclMessage, Declaration, Dossier, User
from ..schemas import DeclOut, MessageIn, QuittanceIn
from ..security import STAFF, W_DOUANE, require

router = APIRouter(tags=["Douane"])
BASE = "/dossiers/{did}/declaration"
REPONSES = {"Transmise": {"Acceptée", "Contrôle", "Rejetée"}, "Acceptée": {"Bon à enlever"}, "Contrôle": {"Bon à enlever", "Rejetée"}}
EN_ATTENTE = {"Transmise", "Acceptée", "Contrôle"}


def _decl(d: Dossier) -> Declaration:
    if not d.declaration:
        raise HTTPException(404, "Aucune déclaration en douane pour ce dossier")
    return d.declaration


def _msg(x: Declaration, sens: str, texte: str) -> None:
    x.messages.append(DeclMessage(sens=sens, texte=texte))


# ---------- Liste et synthèse ----------

@router.get("/declarations", response_model=list[DeclOut])
def lister(statut: str = "", q: str = "", _: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    rows = db.scalars(select(Declaration).order_by(Declaration.id.desc())).all()
    if statut == "en_attente":
        rows = [x for x in rows if x.statut in EN_ATTENTE]
    elif statut:
        rows = [x for x in rows if x.statut == statut]
    if q:
        ql = q.lower()
        rows = [x for x in rows if ql in f"{x.ref} {x.ref_douane} {x.dossier_num} {x.client_nom} {x.quittance_ref} {x.dossier.code_sh}".lower()]
    return rows


@router.get("/declarations/resume")
def resume(_: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    rows = db.scalars(select(Declaration)).all()
    il_y_a_30j = datetime.utcnow() - timedelta(days=30)
    delais = [x.delai_jours for x in rows if x.delai_jours is not None and x.bae_le >= datetime.utcnow() - timedelta(days=90)]
    par = lambda s: sum(x.statut == s for x in rows)  # noqa: E731
    return {
        "brouillons": par("Brouillon"), "transmises": par("Transmise"), "acceptees": par("Acceptée"),
        "controles": par("Contrôle"), "rejetees": par("Rejetée"),
        "bae_30j": sum(bool(x.bae_le and x.bae_le >= il_y_a_30j) for x in rows),
        "delai_moyen_jours": round(sum(delais) / len(delais), 1) if delais else None,
        "attente_plus_3j": sum((x.attente_jours or 0) > 3 for x in rows),
        "quittances_a_payer": sum(x.statut in {"Acceptée", "Contrôle"} and (x.montant_liquide or 0) > 0 and not x.quittance_ref
                                  for x in rows),
        "liquide_30j": float(sum((x.montant_liquide or Decimal(0) for x in rows if x.transmise_le and x.transmise_le >= il_y_a_30j),
                                 Decimal(0))),
        "devise_base": get_params(db)["base"],
    }


# ---------- Déclaration d'un dossier ----------

@router.post(BASE, response_model=DeclOut, status_code=201)
def generer(d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOUANE)), db: Session = Depends(get_db)):
    if d.declaration:
        raise HTTPException(409, "Ce dossier a déjà une déclaration")
    d.declaration = Declaration(ref=f"DUM-{date.today().year}-{d.id:04d}")
    _msg(d.declaration, "interne", "Projet de déclaration généré à partir du dossier")
    audit(db, u, "declaration", d.id, "projet généré")
    db.commit()
    return d.declaration


@router.get(BASE, response_model=DeclOut)
def lire(d: Dossier = Depends(dossier_for)):
    return _decl(d)


@router.get(BASE + "/calcul")
def calcul(d: Dossier = Depends(dossier_for), db: Session = Depends(get_db)):
    return {"liquidation": compute(d, get_params(db)), "controles": controls(d, {x.type for x in d.documents})}


@router.post(BASE + "/transmettre", response_model=DeclOut)
def transmettre(d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOUANE)), db: Session = Depends(get_db)):
    x = _decl(d)
    if x.statut != "Brouillon":
        raise HTTPException(409, f"Transmission impossible : la déclaration est « {x.statut} »")
    bloquants = [c["controle"] for c in controls(d, {y.type for y in d.documents}) if not c["conforme"]]
    if bloquants:
        raise HTTPException(422, {"message": "Contrôles de cohérence non satisfaits", "bloquants": bloquants})
    total = compute(d, get_params(db))["total"]
    ref = gateway.submit(x.ref, {"dossier": d.num, "liquidation": str(total)})
    x.statut, x.transmise_le, x.montant_liquide = "Transmise", datetime.utcnow(), total
    x.bae_le = x.reponse_le = None
    _msg(x, "envoi", f"Déclaration transmise au système douanier (réf. {ref}), liquidation {total:,.0f}".replace(",", " "))
    audit(db, u, "declaration", d.id, "transmission", ref)
    db.commit()
    return x


@router.post(BASE + "/messages", response_model=DeclOut)
def message_douane(body: MessageIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOUANE)),
                   db: Session = Depends(get_db)):
    """Enregistre une réponse du système douanier (point d'entrée de la future passerelle)."""
    x = _decl(d)
    if body.statut not in REPONSES.get(x.statut, set()):
        raise HTTPException(409, f"Réponse « {body.statut} » impossible quand la déclaration est « {x.statut} »")
    if body.statut == "Rejetée" and not body.texte.strip():
        raise HTTPException(422, "Indiquez le motif du rejet")
    if body.statut == "Bon à enlever" and (x.montant_liquide or 0) > 0 and not x.quittance_ref:
        raise HTTPException(422, "Enregistrez d'abord la quittance de paiement des droits et taxes")
    audit(db, u, "declaration", d.id, "message douane", f"{x.statut} -> {body.statut}")
    x.statut = body.statut
    now = datetime.utcnow()
    if body.statut == "Bon à enlever":
        x.bae_le = now
    else:
        x.reponse_le = x.reponse_le or now
    if body.ref_douane.strip():
        x.ref_douane = body.ref_douane.strip()
    _msg(x, "réception", body.texte.strip() or f"Déclaration : {body.statut}"
         + (f" (enregistrée sous {x.ref_douane})" if body.statut == "Acceptée" and x.ref_douane else ""))
    db.commit()
    return x


@router.post(BASE + "/quittance", response_model=DeclOut)
def quittance(body: QuittanceIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOUANE, "Comptable")),
              db: Session = Depends(get_db)):
    """Paiement des droits et taxes : archive la quittance et l'inscrit dans les coûts du dossier."""
    x = _decl(d)
    if x.statut not in {"Acceptée", "Contrôle"}:
        raise HTTPException(409, "La quittance s'enregistre après acceptation de la déclaration")
    if x.quittance_ref:
        raise HTTPException(409, f"Quittance déjà enregistrée ({x.quittance_ref})")
    p = get_params(db)
    x.quittance_ref, x.quittance_montant, x.quittance_date = body.ref.strip(), body.montant, body.date or date.today()
    d.couts.append(Cout(categorie="Droits et taxes", libelle=f"Quittance {x.quittance_ref} ({x.ref})", montant=body.montant,
                        devise=p["base"], date=x.quittance_date, saisi_par=u.email))
    ecart = body.montant - (x.montant_liquide or Decimal(0))
    _msg(x, "interne", f"Quittance {x.quittance_ref} : {body.montant:,.0f} {p['base']} payés".replace(",", " ")
         + (f", écart de {ecart:,.0f} avec la liquidation".replace(",", " ") if ecart else ""))
    audit(db, u, "declaration", d.id, "quittance", f"{x.quittance_ref} : {body.montant}")
    db.commit()
    return x


@router.post(BASE + "/rouvrir", response_model=DeclOut)
def rouvrir(d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOUANE)), db: Session = Depends(get_db)):
    x = _decl(d)
    if x.statut != "Rejetée":
        raise HTTPException(409, "Seule une déclaration rejetée peut être rouverte")
    x.statut, x.transmise_le, x.montant_liquide, x.reponse_le = "Brouillon", None, None, None
    _msg(x, "interne", "Déclaration rouverte pour correction")
    audit(db, u, "declaration", d.id, "réouverture")
    db.commit()
    return x
