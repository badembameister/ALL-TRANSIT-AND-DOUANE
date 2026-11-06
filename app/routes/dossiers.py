import os
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..customs import DOC_TYPES
from ..db import get_db
from ..deps import dossier_for
from ..models import Audit, Client, Document, Dossier, User
from ..schemas import DocumentOut, DossierIn, DossierOut, StatutIn
from ..security import STAFF, W_DOCS, W_DOSSIER, current_user, require

router = APIRouter(tags=["Dossiers et documents"])
EXT = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".docx"}
MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "4"))  # Vercel plafonne les requêtes à 4,5 Mo
MAX_BYTES = MAX_MB * 1024 * 1024
MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
PREFIX = {"Import": "IMP", "Export": "EXP", "Entrepôt": "ENT", "Réexport": "REX"}


@router.get("/dossiers", response_model=list[DossierOut])
def lister(q: str = "", statut: str = "", u: User = Depends(current_user), db: Session = Depends(get_db)):
    st = select(Dossier).join(Client).order_by(Dossier.id.desc())
    if u.role == "Client":
        st = st.where(Dossier.client_id == u.client_id)
    if statut:
        st = st.where(Dossier.statut == statut)
    if q:
        like = f"%{q}%"
        st = st.where(or_(Dossier.num.ilike(like), Dossier.ref.ilike(like), Dossier.designation.ilike(like),
                          Dossier.code_sh.like(like), Client.nom.ilike(like)))
    return db.scalars(st).all()


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


@router.patch("/dossiers/{did}/statut", response_model=DossierOut)
def statut(body: StatutIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_DOSSIER)),
           db: Session = Depends(get_db)):
    audit(db, u, "dossier", d.id, "statut", f"{d.statut} -> {body.statut}")
    d.statut = body.statut
    db.commit()
    return d


@router.get("/dossiers/{did}/journal")
def journal(d: Dossier = Depends(dossier_for), u: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    rows = db.scalars(select(Audit).where(Audit.entite_id == d.id).order_by(Audit.id.desc())).all()
    return [{"ts": a.ts, "utilisateur": a.utilisateur, "entite": a.entite, "action": a.action, "detail": a.detail}
            for a in rows if a.entite in {"dossier", "transit", "declaration", "facture", "document"}]


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
