"""Clients et partenaires (cahier des charges, point 3) : fiches juridiques, fiscales et bancaires, contacts
multiples, documents d'agrément, historique des opérations et situation financière."""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..fmt import milliers
from ..audit import audit
from ..db import get_db
from ..deps import get_params
from ..models import Client, Contact, Conteneur, Declaration, Dossier, Facture, PiecePartenaire, Transit, User, Vehicule
from ..schemas import ClientIn, ClientOut, ContactIn, ContactOut, PieceOut
from ..security import STAFF, W_CLIENT, require
from .dossiers import EXT, MAX_BYTES, MAX_MB, MIME

router = APIRouter(prefix="/clients", tags=["Clients et partenaires"])
PREFIXE = {"Client": "C", "Fournisseur": "F", "Transporteur": "T", "Agent étranger": "A", "Destinataire": "D", "Administration": "X"}
TYPES_PIECES = ["Agrément", "Carte de commerçant", "RCCM", "Attestation fiscale", "Attestation d'assurance", "Contrat", "Autre"]
ALERTE_JOURS = 30


def _client(db: Session, cid: int) -> Client:
    c = db.get(Client, cid)
    if not c:
        raise HTTPException(404, "Partenaire introuvable")
    return c


def _doublon(db: Session, body: ClientIn, sauf: int = 0) -> None:
    if body.nif.strip():
        autre = db.scalars(select(Client).where(func.lower(Client.nif) == body.nif.strip().lower(), Client.type == body.type,
                                                Client.id != sauf)).first()
        if autre:
            raise HTTPException(409, f"NIF déjà utilisé par {autre.code} {autre.nom}")


@router.get("", response_model=list[ClientOut])
def lister(q: str = "", type: str = "", actifs: bool = False, _: User = Depends(require(*STAFF)),
           db: Session = Depends(get_db)):
    st = select(Client).order_by(Client.nom)
    if type:
        st = st.where(Client.type == type) if type != "Client" else st.where(or_(Client.type == "Client", Client.type.is_(None)))
    if actifs:
        st = st.where(or_(Client.actif.is_(True), Client.actif.is_(None)))
    if q:
        like = f"%{q}%"
        # Recherche aussi par n° de dossier, conteneur ou référence douanière (cahier des charges, point 3)
        par_dossier = (select(Dossier.client_id).outerjoin(Declaration).outerjoin(Transit)
                       .where(or_(Dossier.num.ilike(like), Dossier.ref.ilike(like), Declaration.ref.ilike(like),
                                  Declaration.ref_douane.ilike(like), Transit.num.ilike(like), Transit.ref_douane.ilike(like),
                                  Dossier.id.in_(select(Conteneur.dossier_id).where(Conteneur.numero.ilike(like))))))
        st = st.where(or_(Client.nom.ilike(like), Client.code.ilike(like), Client.nif.ilike(like), Client.rc.ilike(like),
                          Client.ville.ilike(like), Client.id.in_(par_dossier)))
    return db.scalars(st).all()


@router.post("", response_model=ClientOut, status_code=201)
def creer(body: ClientIn, u: User = Depends(require(*W_CLIENT)), db: Session = Depends(get_db)):
    _doublon(db, body)
    c = Client(**body.model_dump())
    db.add(c)
    db.flush()
    c.code = f"{PREFIXE[body.type]}{c.id:04d}"
    if body.contact.strip():
        c.contacts.append(Contact(nom=body.contact.strip(), principal=True))
    audit(db, u, "client", c.id, "création", f"{c.code} {c.nom} ({c.type})")
    db.commit()
    return c


@router.get("/{cid}", response_model=ClientOut)
def lire(cid: int, _: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    return _client(db, cid)


@router.put("/{cid}", response_model=ClientOut)
def modifier(cid: int, body: ClientIn, u: User = Depends(require(*W_CLIENT)), db: Session = Depends(get_db)):
    c = _client(db, cid)
    _doublon(db, body, sauf=c.id)
    changes = [k for k, v in body.model_dump().items() if getattr(c, k) != v]
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, u, "client", c.id, "modification", ", ".join(changes) or "aucun changement")
    db.commit()
    return c


@router.get("/{cid}/fiche")
def fiche(cid: int, _: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    """Fiche complète : contacts, documents, historique des opérations et situation financière."""
    c = _client(db, cid)
    rates = get_params(db)["rates"]
    base = lambda m, dev: Decimal(str(m)) * Decimal(str(rates.get(dev, 1)))  # noqa: E731
    if (c.type or "Client") == "Client":
        dossiers = db.scalars(select(Dossier).where(Dossier.client_id == c.id).order_by(Dossier.id.desc())).all()
    else:  # partenaire : dossiers où il apparaît comme fournisseur, destinataire, transporteur ou agent
        n = c.nom.lower()
        dossiers = db.scalars(select(Dossier).where(or_(
            func.lower(Dossier.fournisseur) == n, func.lower(Dossier.destinataire) == n,
            func.lower(Dossier.transporteur) == n, func.lower(Dossier.agent_douanier) == n)).order_by(Dossier.id.desc())).all()
    factures = db.scalars(select(Facture).where(Facture.client_id == c.id)).all()
    encours = sum((base(f.solde, f.devise) for f in factures if f.solde > 0), Decimal(0))
    retard = [f for f in factures if f.jours_retard > 0]
    limite = date.today() + timedelta(days=ALERTE_JOURS)
    alertes = []
    if c.plafond_credit and encours > c.plafond_credit:
        alertes.append(f"Encours de {milliers(encours)} au-delà du plafond de crédit ({milliers(c.plafond_credit)})")
    if retard:
        alertes.append(f"{len(retard)} facture(s) en retard de paiement")
    alertes += [f"{p.type} {'expiré' if p.expire else 'expire'} le {p.expiration:%d/%m/%Y}" for p in c.pieces
                if p.expiration and p.expiration <= limite]
    vehicules = db.scalars(select(Vehicule).where(func.lower(Vehicule.transporteur) == c.nom.lower())).all() \
        if c.type == "Transporteur" else []
    return {
        "client": ClientOut.model_validate(c).model_dump(),
        "contacts": [ContactOut.model_validate(x).model_dump() for x in c.contacts],
        "pieces": [PieceOut.model_validate(x).model_dump() for x in c.pieces],
        "types_pieces": TYPES_PIECES,
        "dossiers": [{"id": d.id, "num": d.num, "type": d.type, "statut": d.statut, "designation": d.designation,
                      "created_at": d.created_at, "facture_statut": d.facture_statut} for d in dossiers[:100]],
        "stats": {
            "dossiers": len(dossiers), "dossiers_ouverts": sum(d.statut not in {"Livré", "Clôturé"} for d in dossiers),
            "ca_facture": float(sum((base(f.total, f.devise) for f in factures), Decimal(0))),
            "ca_12_mois": float(sum((base(f.total, f.devise) for f in factures
                                     if f.date_emission >= date.today() - timedelta(days=365)), Decimal(0))),
            "encours": float(encours), "factures_en_retard": len(retard),
            "montant_retard": float(sum((base(f.solde, f.devise) for f in retard), Decimal(0))),
            "dernier_dossier": dossiers[0].created_at if dossiers else None,
            "vehicules": len(vehicules),
        },
        "alertes": alertes,
        "devise_base": get_params(db)["base"],
    }


# ---------- Contacts ----------

def _principal_unique(c: Client, garde: Contact) -> None:
    if garde.principal:
        for x in c.contacts:
            if x is not garde:
                x.principal = False


@router.post("/{cid}/contacts", response_model=ContactOut, status_code=201)
def ajouter_contact(cid: int, body: ContactIn, u: User = Depends(require(*W_CLIENT)), db: Session = Depends(get_db)):
    c = _client(db, cid)
    x = Contact(**(body.model_dump() | {"principal": body.principal or not c.contacts}))
    c.contacts.append(x)
    _principal_unique(c, x)
    audit(db, u, "client", c.id, "contact ajouté", body.nom)
    db.commit()
    return x


@router.put("/{cid}/contacts/{xid}", response_model=ContactOut)
def modifier_contact(cid: int, xid: int, body: ContactIn, u: User = Depends(require(*W_CLIENT)), db: Session = Depends(get_db)):
    c = _client(db, cid)
    x = next((y for y in c.contacts if y.id == xid), None)
    if not x:
        raise HTTPException(404, "Contact introuvable")
    for k, v in body.model_dump().items():
        setattr(x, k, v)
    _principal_unique(c, x)
    audit(db, u, "client", c.id, "contact modifié", body.nom)
    db.commit()
    return x


@router.delete("/{cid}/contacts/{xid}", status_code=204)
def supprimer_contact(cid: int, xid: int, u: User = Depends(require(*W_CLIENT)), db: Session = Depends(get_db)):
    c = _client(db, cid)
    x = next((y for y in c.contacts if y.id == xid), None)
    if not x:
        raise HTTPException(404, "Contact introuvable")
    c.contacts.remove(x)
    if x.principal and c.contacts:
        c.contacts[0].principal = True
    audit(db, u, "client", c.id, "contact supprimé", x.nom)
    db.commit()


# ---------- Documents (agrément, carte de commerçant, attestations, contrats) ----------

@router.post("/{cid}/pieces", response_model=PieceOut, status_code=201)
async def deposer(cid: int, type: str = Form(...), expiration: str = Form(""), fichier: UploadFile = File(...),
                  u: User = Depends(require(*W_CLIENT, "Comptable")), db: Session = Depends(get_db)):
    c = _client(db, cid)
    if type not in TYPES_PIECES:
        raise HTTPException(422, f"Type de document inconnu. Valeurs : {', '.join(TYPES_PIECES)}")
    ext = Path(fichier.filename or "").suffix.lower()
    if ext not in EXT:
        raise HTTPException(415, f"Format refusé. Formats acceptés : {', '.join(sorted(EXT))}")
    content = await fichier.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, f"Fichier trop volumineux ({MAX_MB} Mo maximum)")
    try:
        exp = date.fromisoformat(expiration) if expiration else None
    except ValueError:
        raise HTTPException(422, "Date d'expiration invalide (AAAA-MM-JJ)")
    p = PiecePartenaire(type=type, nom_fichier=fichier.filename, contenu=content, expiration=exp, depose_par=u.email)
    c.pieces.append(p)
    audit(db, u, "client", c.id, "document", f"{type} : {fichier.filename}")
    db.commit()
    return p


def _piece(db: Session, cid: int, pid: int) -> PiecePartenaire:
    p = db.get(PiecePartenaire, pid)
    if not p or p.client_id != cid:
        raise HTTPException(404, "Document introuvable")
    return p


@router.get("/{cid}/pieces/{pid}")
def telecharger(cid: int, pid: int, _: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    p = _piece(db, cid, pid)
    ext = Path(p.nom_fichier).suffix.lower()
    return Response(p.contenu, media_type=MIME.get(ext, "application/octet-stream"),
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(p.nom_fichier)}"})


@router.delete("/{cid}/pieces/{pid}", status_code=204)
def supprimer_piece(cid: int, pid: int, u: User = Depends(require(*W_CLIENT)), db: Session = Depends(get_db)):
    p = _piece(db, cid, pid)
    audit(db, u, "client", cid, "document supprimé", f"{p.type} : {p.nom_fichier}")
    db.delete(p)
    db.commit()
