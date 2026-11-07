"""Module transit : déclaration, itinéraire et bureaux, scellés, garantie, suivi jusqu'à l'apurement,
incidents, alertes et historique des échanges avec le système douanier (cahier des charges, point 5)."""
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import dossier_for
from ..gateway import gateway
from ..models import OPEN_TRANSIT, Chauffeur, Dossier, Transit, User, Vehicule
from ..schemas import IncidentIn, PassageIn, TransitIn, TransitionIn, TransitMessageIn, TransitOut
from ..security import STAFF, W_TRANSIT, require

router = APIRouter(tags=["Transit"])
BASE = "/dossiers/{did}/transit"
ETAPES = ["En préparation", "Déposée", "Acceptée", "En circulation", "Contrôlée", "Arrivée à destination", "Apurée"]
MODIFIABLE = {"En préparation", "Rejetée"}


def _transit(d: Dossier) -> Transit:
    if not d.transit:
        raise HTTPException(404, "Aucune déclaration de transit pour ce dossier")
    return d.transit


def autorisees(statut: str) -> set[str]:
    if statut == "Rejetée":
        return {"En préparation"}
    i = ETAPES.index(statut)
    nxt = {ETAPES[i + 1]} if i < len(ETAPES) - 1 else set()
    if statut == "En circulation":
        nxt.add("Arrivée à destination")  # arrivée sans contrôle en route
    if statut in {"Déposée", "Acceptée"}:
        nxt.add("Rejetée")  # seule la douane rejette, avant le départ
    return nxt


def _msg(t: Transit, sens: str, texte: str) -> None:
    t.messages = [*(t.messages or []), {"ts": datetime.utcnow().isoformat(timespec="seconds") + "Z", "sens": sens,
                                         "texte": texte}]


def _appliquer(t: Transit, body: TransitIn, d: Dossier, db: Session) -> None:
    data = body.model_dump(exclude={"bureaux_passage"})
    if body.vehicule_id:
        v = db.get(Vehicule, body.vehicule_id)
        if not v:
            raise HTTPException(404, "Véhicule introuvable")
        data["vehicule"] = data["vehicule"] or v.immatriculation
        data["transporteur"] = data["transporteur"] or v.transporteur
    if body.chauffeur_id and not db.get(Chauffeur, body.chauffeur_id):
        raise HTTPException(404, "Chauffeur introuvable")
    # Valeurs reprises du dossier quand elles ne sont pas saisies
    data["expediteur"] = data["expediteur"] or d.fournisseur
    data["destinataire"] = data["destinataire"] or d.destinataire or d.client.nom
    data["transporteur"] = data["transporteur"] or d.transporteur
    data["marchandises"] = data["marchandises"] or f"{d.designation} : {d.colis} colis, {float(d.poids):g} kg, SH {d.code_sh}"
    for k, v in data.items():
        setattr(t, k, v)
    anciens = {p["bureau"]: p.get("date") for p in t.passages or []}
    t.passages = [{"bureau": b.strip(), "date": anciens.get(b.strip())} for b in body.bureaux_passage if b.strip()]


def _depart_ok(t: Transit) -> None:
    manque = [lib for ok, lib in ((t.vehicule or t.vehicule_id, "véhicule"), (t.scelle, "numéro de scellé"),
                                  (t.garantie, "garantie")) if not ok]
    if manque:
        raise HTTPException(422, f"Mise en circulation impossible, à compléter : {', '.join(manque)}")


@router.get("/transits", response_model=list[TransitOut])
def lister(statut: str = "", alerte: bool = False, _: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    rows = db.scalars(select(Transit).order_by(Transit.id.desc())).all()
    if statut == "ouverts":
        rows = [t for t in rows if t.statut in OPEN_TRANSIT]
    elif statut:
        rows = [t for t in rows if t.statut == statut]
    if alerte:
        rows = [t for t in rows if t.en_retard or t.scelle_casse]
    return rows


@router.post(BASE, response_model=TransitOut, status_code=201)
def creer(body: TransitIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_TRANSIT)),
          db: Session = Depends(get_db)):
    if d.transit:
        raise HTTPException(409, "Ce dossier a déjà une déclaration de transit")
    t = Transit(dossier=d, bureau_depart=body.bureau_depart, bureau_destination=body.bureau_destination)
    _appliquer(t, body, d, db)
    db.add(t)
    db.flush()
    t.num = f"TR-{date.today().year}-{t.id:04d}"
    _msg(t, "interne", f"Déclaration {t.num} créée : {t.bureau_depart} → {t.bureau_destination}")
    audit(db, u, "transit", d.id, "création", t.num)
    db.commit()
    return t


@router.get(BASE, response_model=TransitOut)
def lire(d: Dossier = Depends(dossier_for)):
    return _transit(d)


@router.put(BASE, response_model=TransitOut)
def modifier(body: TransitIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_TRANSIT)),
             db: Session = Depends(get_db)):
    t = _transit(d)
    if t.statut not in MODIFIABLE:
        raise HTTPException(409, f"Déclaration « {t.statut} » : modification possible seulement en préparation ou après rejet")
    _appliquer(t, body, d, db)
    audit(db, u, "transit", d.id, "modification", t.num)
    db.commit()
    return t


@router.post(BASE + "/transition", response_model=TransitOut)
def transition(body: TransitionIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_TRANSIT)),
               db: Session = Depends(get_db)):
    t = _transit(d)
    ok = autorisees(t.statut)
    if body.to not in ok:
        raise HTTPException(409, f"Passage impossible depuis « {t.statut} ». Étapes permises : {', '.join(sorted(ok)) or 'aucune'}")
    if body.to == "Rejetée" and not body.motif.strip():
        raise HTTPException(422, "Indiquez le motif du rejet communiqué par la douane")
    if body.to == "En circulation":
        _depart_ok(t)
    if body.to == "Apurée" and any(not p.get("date") for p in t.passages or []):
        manquants = ", ".join(p["bureau"] for p in t.passages if not p.get("date"))
        raise HTTPException(422, f"Apurement impossible : passage non constaté à {manquants}")
    audit(db, u, "transit", d.id, "statut", f"{t.statut} -> {body.to}")
    t.statut = body.to
    today = date.today()
    if body.to == "Déposée":
        ref = gateway.submit(t.num, {"dossier": d.num, "type": "transit", "depart": t.bureau_depart,
                                     "destination": t.bureau_destination, "scelles": t.scelle})
        _msg(t, "envoi", f"Déclaration de transit transmise au système douanier (réf. {ref})")
    elif body.to == "Acceptée":
        t.ref_douane = body.ref_douane.strip() or t.ref_douane or f"T-{t.num}"
        _msg(t, "réception", f"Déclaration acceptée, enregistrée sous {t.ref_douane}")
    elif body.to == "Rejetée":
        _msg(t, "réception", f"Déclaration rejetée : {body.motif.strip()}")
    elif body.to == "En préparation":
        _msg(t, "interne", "Déclaration reprise pour correction")
    elif body.to == "En circulation":
        t.depart, t.arrivee, t.apurement = today, None, None
        _msg(t, "interne", f"Départ du bureau {t.bureau_depart}, échéance le {t.echeance:%d/%m/%Y}")
    elif body.to == "Contrôlée":
        _msg(t, "réception", f"Contrôle douanier en route{' : ' + body.motif.strip() if body.motif.strip() else ''}")
    elif body.to == "Arrivée à destination":
        t.arrivee = today
        _msg(t, "réception", f"Arrivée constatée au bureau {t.bureau_destination}")
    elif body.to == "Apurée":
        t.apurement = today
        _msg(t, "réception", "Transit apuré : garantie libérable")
    db.commit()
    return t


@router.post(BASE + "/passages", response_model=TransitOut)
def passage(body: PassageIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_TRANSIT)),
            db: Session = Depends(get_db)):
    t = _transit(d)
    if t.statut not in {"En circulation", "Contrôlée", "Arrivée à destination"}:
        raise HTTPException(409, "Un passage se constate entre le départ et l'apurement")
    ps = [dict(p) for p in t.passages or []]
    cible = next((p for p in ps if p["bureau"].lower() == body.bureau.strip().lower()), None)
    if not cible:
        raise HTTPException(404, f"« {body.bureau} » n'est pas un bureau de passage de ce transit")
    if cible.get("date"):
        raise HTTPException(409, f"Passage à {cible['bureau']} déjà constaté le {cible['date']}")
    cible["date"] = date.today().isoformat()
    t.passages = ps
    _msg(t, "réception", f"Passage constaté au bureau {cible['bureau']}")
    audit(db, u, "transit", d.id, "passage", cible["bureau"])
    db.commit()
    return t


@router.post(BASE + "/incidents", response_model=TransitOut, status_code=201)
def incident(body: IncidentIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_TRANSIT)),
             db: Session = Depends(get_db)):
    t = _transit(d)
    t.incidents = [{"date": date.today().isoformat(), **body.model_dump()}, *(t.incidents or [])]
    audit(db, u, "transit", d.id, "incident", body.type)
    db.commit()
    return t


@router.post(BASE + "/messages", response_model=TransitOut, status_code=201)
def message(body: TransitMessageIn, d: Dossier = Depends(dossier_for), u: User = Depends(require(*W_TRANSIT)),
            db: Session = Depends(get_db)):
    """Consigne un échange avec la douane (en attendant la passerelle SYDONIA, ou pour une note interne)."""
    t = _transit(d)
    _msg(t, body.sens, body.texte.strip())
    audit(db, u, "transit", d.id, "message", body.sens)
    db.commit()
    return t


def resume_transits(db: Session) -> dict:
    rows = db.scalars(select(Transit)).all()
    return {"en_cours": sum(t.statut in OPEN_TRANSIT for t in rows), "en_retard": sum(t.en_retard for t in rows),
            "en_preparation": sum(t.statut in {"En préparation", "Déposée", "Acceptée"} for t in rows),
            "apures_30j": sum(bool(t.apurement and (date.today() - t.apurement).days <= 30) for t in rows),
            "rejetes": sum(t.statut == "Rejetée" for t in rows)}


@router.get("/transits/resume")
def resume(_: User = Depends(require(*STAFF)), db: Session = Depends(get_db)) -> dict:
    return resume_transits(db)

