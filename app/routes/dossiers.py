import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..customs import DOC_TYPES
from ..db import get_db
from ..deps import dossier_for, get_params
from ..jalons import CLES, jalons
from ..models import Audit, Client, Conteneur, Cout, Declaration, Document, Dossier, Mission, Transit, User
from ..schemas import CoutIn, CoutOut, DocumentOut, DossierIn, DossierOut, JalonIn, StatutIn
from ..security import STAFF, W_DOCS, W_DOSSIER, W_FACT, current_user, require

router = APIRouter(tags=["Dossiers et documents"])
EXT = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".docx"}
MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "4"))  # Vercel plafonne les requêtes à 4,5 Mo
MAX_BYTES = MAX_MB * 1024 * 1024
MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
PREFIX = {"Import": "IMP", "Export": "EXP", "Entrepôt": "ENT", "Réexport": "REX"}


@router.get("/dossiers", response_model=list[DossierOut])
def lister(q: str = "", statut: str = "", type: str = "", client_id: int = 0, u: User = Depends(current_user),
           db: Session = Depends(get_db)):
    st = (select(Dossier).join(Client).outerjoin(Declaration).outerjoin(Transit).order_by(Dossier.id.desc()))
    if u.role == "Client":
        st = st.where(Dossier.client_id == u.client_id)
    if statut:
        st = st.where(Dossier.statut == statut)
    if type:
        st = st.where(Dossier.type == type)
    if client_id:
        st = st.where(Dossier.client_id == client_id)
    if q:
        like = f"%{q}%"
        par_conteneur = select(Conteneur.dossier_id).where(Conteneur.numero.ilike(like))
        st = st.where(or_(Dossier.num.ilike(like), Dossier.ref.ilike(like), Dossier.designation.ilike(like),
                          Dossier.code_sh.like(like), Client.nom.ilike(like), Client.code.ilike(like),
                          Declaration.ref.ilike(like), Transit.num.ilike(like), Transit.ref_douane.ilike(like),
                          Dossier.id.in_(par_conteneur)))
    return db.scalars(st).unique().all()


@router.post("/dossiers", response_model=DossierOut, status_code=201)
def creer(body: DossierIn, u: User = Depends(require(*W_DOSSIER)), db: Session = Depends(get_db)):
    if not db.get(Client, body.client_id):
        raise HTTPException(422, "Client inconnu")
    data = body.model_dump()
    data["code_sh"] = "".join(ch for ch in data["code_sh"] if ch.isdigit())
    d = Dossier(**data)
    db.add(d)
    db.flush()
    d.num = f"{PREFIX.get(body.type, 'TRN')}-{date.today().year}-{d.id:04d}"
    audit(db, u, "dossier", d.id, "création", d.num)
    db.commit()
    return d


@router.get("/dossiers/{did}", response_model=DossierOut)
def lire(d: Dossier = Depends(dossier_for)):
    return d


@router.put("/dossiers/{did}", response_model=DossierOut)
def modifier(body: DossierIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOSSIER)),
             db: Session = Depends(get_db)):
    if d.statut == "Clôturé":
        raise HTTPException(409, "Dossier clôturé : rouvrez-le (statut « En cours ») avant de le modifier")
    if not db.get(Client, body.client_id):
        raise HTTPException(422, "Client inconnu")
    if body.client_id != d.client_id and d.facture:
        raise HTTPException(409, "Dossier déjà facturé : le client ne peut plus changer")
    data = body.model_dump()
    data["code_sh"] = "".join(ch for ch in data["code_sh"] if ch.isdigit())
    changes = [k for k, v in data.items() if getattr(d, k) != v]
    for k, v in data.items():
        setattr(d, k, v)
    audit(db, u, "dossier", d.id, "modification", ", ".join(changes) or "aucun changement")
    db.commit()
    return d


@router.patch("/dossiers/{did}/statut", response_model=DossierOut)
def statut(body: StatutIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOSSIER)),
           db: Session = Depends(get_db)):
    audit(db, u, "dossier", d.id, "statut", f"{d.statut} -> {body.statut}")
    d.statut = body.statut
    db.commit()
    return d


@router.get("/dossiers/{did}/jalons")
def lire_jalons(d: Dossier = Depends(dossier_for), db: Session = Depends(get_db)):
    return jalons(db, d)


@router.put("/dossiers/{did}/jalons/{cle}")
def saisir_jalon(cle: str, body: JalonIn, d: Dossier = Depends(dossier_for),
                 u: User = Depends(require(*W_DOSSIER, "Agent opérationnel", "Déclarant en douane")),
                 db: Session = Depends(get_db)):
    if cle not in CLES:
        raise HTTPException(404, "Étape inconnue")
    j = dict(d.jalons or {})
    j[cle] = {k: (v.isoformat() if v else None) for k, v in body.model_dump().items()}
    d.jalons = j
    audit(db, u, "dossier", d.id, "étape", f"{cle} : prévue {body.prevue or '-'}, réelle {body.reelle or '-'}")
    db.commit()
    return jalons(db, d)


def _base(db: Session, montant, devise: str) -> Decimal:
    return Decimal(str(montant)) * Decimal(str(get_params(db)["rates"].get(devise, 1)))


@router.get("/dossiers/{did}/couts")
def couts(d: Dossier = Depends(dossier_for), _: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    """Coûts engagés, chiffre d'affaires facturé et marge du dossier, en devise de base."""
    p = get_params(db)
    lignes = [CoutOut.model_validate(c).model_dump() | {"montant_base": float(_base(db, c.montant, c.devise))} for c in d.couts]
    total_couts = sum((Decimal(str(x["montant_base"])) for x in lignes), Decimal(0))
    ca = _base(db, d.facture.total, d.facture.devise) if d.facture else Decimal(0)
    debours = Decimal(0)
    if d.facture:
        debours = sum((_base(db, x.montant, d.facture.devise) for x in d.facture.lignes if "débours" in x.libelle.lower()), Decimal(0))
    marge = ca - total_couts
    return {"devise_base": p["base"], "couts": lignes, "total_couts": float(total_couts), "facture": float(ca),
            "dont_debours": float(debours), "marge": float(marge),
            "taux_marge": round(float(marge / ca * 100), 1) if ca else None}


@router.post("/dossiers/{did}/couts", response_model=CoutOut, status_code=201)
def ajouter_cout(body: CoutIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOSSIER, *W_FACT)),
                 db: Session = Depends(get_db)):
    if body.devise not in get_params(db)["rates"]:
        raise HTTPException(422, "Devise non paramétrée")
    c = Cout(**body.model_dump(exclude={"date"}), date=body.date or date.today(), saisi_par=u.email)
    d.couts.append(c)
    audit(db, u, "dossier", d.id, "coût", f"{body.libelle} : {body.montant} {body.devise}")
    db.commit()
    return c


@router.delete("/dossiers/{did}/couts/{cid}", status_code=204)
def supprimer_cout(cid: int, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOSSIER, *W_FACT)),
                   db: Session = Depends(get_db)):
    c = next((x for x in d.couts if x.id == cid), None)
    if not c:
        raise HTTPException(404, "Coût introuvable")
    audit(db, u, "dossier", d.id, "suppression coût", f"{c.libelle} : {c.montant} {c.devise}")
    d.couts.remove(c)
    db.commit()


@router.get("/dossiers/{did}/journal")
def journal(d: Dossier = Depends(dossier_for), u: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    missions = select(Mission.id).where(Mission.dossier_id == d.id)
    conteneurs = select(Conteneur.id).where(Conteneur.dossier_id == d.id)
    rows = db.scalars(select(Audit).where(or_(
        Audit.entite.in_(["dossier", "transit", "declaration", "facture", "document"]) & (Audit.entite_id == d.id),
        (Audit.entite == "mission") & Audit.entite_id.in_(missions),
        (Audit.entite == "conteneur") & Audit.entite_id.in_(conteneurs),
    )).order_by(Audit.id.desc())).all()
    return [{"ts": a.ts, "utilisateur": a.utilisateur, "entite": a.entite, "action": a.action, "detail": a.detail}
            for a in rows]


@router.get("/dossiers/{did}/documents", response_model=list[DocumentOut])
def documents(d: Dossier = Depends(dossier_for)):
    return d.documents


@router.post("/dossiers/{did}/documents", response_model=DocumentOut, status_code=201)
async def televerser(type: str = Form(...), fichier: UploadFile = File(...), d: Dossier = Depends(dossier_for),
                     u: User = Depends(require(*W_DOCS)), db: Session = Depends(get_db)):
    if type not in DOC_TYPES:
        raise HTTPException(422, f"Type de document inconnu. Valeurs : {', '.join(DOC_TYPES)}")
    ext = Path(fichier.filename or "").suffix.lower()
    if ext not in EXT:
        raise HTTPException(415, f"Format refusé. Formats acceptés : {', '.join(sorted(EXT))}")
    content = await fichier.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, f"Fichier trop volumineux ({MAX_MB} Mo maximum)")
    version = 1 + sum(1 for x in d.documents if x.type == type)
    doc = Document(dossier_id=d.id, type=type, version=version, nom_fichier=fichier.filename, contenu=content,
                   depose_par=u.email)
    db.add(doc)
    audit(db, u, "document", d.id, "dépôt", f"{type} v{version}")
    db.commit()
    return doc


@router.get("/documents/{doc_id}/download")
def telecharger(doc_id: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc or (u.role == "Client" and doc.dossier.client_id != u.client_id):
        raise HTTPException(404, "Document introuvable")
    ext = Path(doc.nom_fichier).suffix.lower()
    return Response(doc.contenu, media_type=MIME.get(ext, "application/octet-stream"),
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc.nom_fichier)}"})
