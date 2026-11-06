"""Transport et suivi opérationnel : parc (véhicules, chauffeurs), conteneurs, missions d'enlèvement et de
livraison, preuves de livraison et positions GPS (cahier des charges, point 8)."""
import base64
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import dossier_for
from ..models import MISSION_OUVERTE, Chauffeur, Conteneur, Dossier, Mission, User, Vehicule
from ..schemas import (ChauffeurIn, ChauffeurOut, ConteneurIn, ConteneurOut, LivraisonIn, MissionIn,
                       MissionIncidentIn, MissionOut, MissionStatutIn, PositionIn, VehiculeIn, VehiculeOut)
from ..security import STAFF, W_OPS, require

router = APIRouter(tags=["Transport et opérations"])
LIRE = require(*STAFF)
ECRIRE = require(*W_OPS)
ALERTE_JOURS = 30  # échéances (assurance, visite technique, permis) signalées à l'avance


def _get(db: Session, model, oid: int, nom: str):
    obj = db.get(model, oid)
    if not obj:
        raise HTTPException(404, f"{nom} introuvable")
    return obj


def _commit(db: Session, doublon: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, doublon)


# ---------- Chauffeurs ----------

@router.get("/chauffeurs", response_model=list[ChauffeurOut])
def chauffeurs(actifs: bool = False, _: User = Depends(LIRE), db: Session = Depends(get_db)):
    st = select(Chauffeur).order_by(Chauffeur.nom)
    return db.scalars(st.where(Chauffeur.actif) if actifs else st).all()


@router.post("/chauffeurs", response_model=ChauffeurOut, status_code=201)
def creer_chauffeur(body: ChauffeurIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    c = Chauffeur(**body.model_dump())
    db.add(c)
    db.flush()
    audit(db, u, "chauffeur", c.id, "création", c.nom)
    db.commit()
    return c


@router.put("/chauffeurs/{cid}", response_model=ChauffeurOut)
def modifier_chauffeur(cid: int, body: ChauffeurIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    c = _get(db, Chauffeur, cid, "Chauffeur")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, u, "chauffeur", c.id, "modification", c.nom)
    db.commit()
    return c


# ---------- Véhicules ----------

@router.get("/vehicules", response_model=list[VehiculeOut])
def vehicules(actifs: bool = False, _: User = Depends(LIRE), db: Session = Depends(get_db)):
    st = select(Vehicule).order_by(Vehicule.immatriculation)
    return db.scalars(st.where(Vehicule.actif) if actifs else st).all()


@router.post("/vehicules", response_model=VehiculeOut, status_code=201)
def creer_vehicule(body: VehiculeIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    v = Vehicule(**body.model_dump())
    db.add(v)
    _commit(db, f"Le véhicule {body.immatriculation} existe déjà")
    audit(db, u, "vehicule", v.id, "création", v.immatriculation)
    db.commit()
    return v


@router.put("/vehicules/{vid}", response_model=VehiculeOut)
def modifier_vehicule(vid: int, body: VehiculeIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    v = _get(db, Vehicule, vid, "Véhicule")
    for k, val in body.model_dump().items():
        setattr(v, k, val)
    audit(db, u, "vehicule", v.id, "modification", v.immatriculation)
    _commit(db, f"Le véhicule {body.immatriculation} existe déjà")
    return v


# ---------- Conteneurs ----------

def _dates_conteneur(b: ConteneurIn) -> None:
    if b.sortie and (not b.arrivee or b.sortie < b.arrivee):
        raise HTTPException(422, "La date de sortie doit suivre la date d'arrivée au port")
    if b.retour and (not b.sortie or b.retour < b.sortie):
        raise HTTPException(422, "La date de restitution doit suivre la date de sortie")


@router.get("/conteneurs", response_model=list[ConteneurOut])
def conteneurs(q: str = "", statut: str = "", _: User = Depends(LIRE), db: Session = Depends(get_db)):
    st = select(Conteneur).outerjoin(Dossier).order_by(Conteneur.id.desc())
    if q:
        like = f"%{q}%"
        st = st.where(or_(Conteneur.numero.ilike(like), Conteneur.bl.ilike(like), Conteneur.compagnie.ilike(like),
                          Dossier.num.ilike(like)))
    rows = db.scalars(st).all()
    return [c for c in rows if c.statut == statut] if statut else rows


@router.post("/conteneurs", response_model=ConteneurOut, status_code=201)
def creer_conteneur(body: ConteneurIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    _dates_conteneur(body)
    if body.dossier_id:
        _get(db, Dossier, body.dossier_id, "Dossier")
    c = Conteneur(**body.model_dump())
    db.add(c)
    _commit(db, f"Le conteneur {body.numero} est déjà enregistré")
    audit(db, u, "conteneur", c.id, "création", c.numero)
    db.commit()
    return c


@router.put("/conteneurs/{cid}", response_model=ConteneurOut)
def modifier_conteneur(cid: int, body: ConteneurIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    c = _get(db, Conteneur, cid, "Conteneur")
    _dates_conteneur(body)
    if body.dossier_id:
        _get(db, Dossier, body.dossier_id, "Dossier")
    avant = c.statut
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(db, u, "conteneur", c.id, "modification", f"{c.numero} : {avant} -> {c.statut}")
    _commit(db, f"Le conteneur {body.numero} est déjà enregistré")
    return c


@router.get("/dossiers/{did}/conteneurs", response_model=list[ConteneurOut])
def conteneurs_dossier(d: Dossier = Depends(dossier_for), db: Session = Depends(get_db)):
    return db.scalars(select(Conteneur).where(Conteneur.dossier_id == d.id).order_by(Conteneur.id)).all()


# ---------- Missions ----------

def _verifier(db: Session, b: MissionIn, sauf: Optional[int] = None) -> None:
    """Références existantes, ressources actives et pas de double affectation le même jour."""
    if b.dossier_id:
        _get(db, Dossier, b.dossier_id, "Dossier")
    if b.conteneur_id:
        c = _get(db, Conteneur, b.conteneur_id, "Conteneur")
        if b.dossier_id and c.dossier_id and c.dossier_id != b.dossier_id:
            raise HTTPException(422, f"Le conteneur {c.numero} appartient à un autre dossier")
    for champ, model, nom in (("vehicule_id", Vehicule, "Véhicule"), ("chauffeur_id", Chauffeur, "Chauffeur")):
        oid = getattr(b, champ)
        if not oid:
            continue
        obj = _get(db, model, oid, nom)
        if not obj.actif:
            raise HTTPException(422, f"{nom} inactif : choisissez une autre ressource")
        st = select(Mission).where(getattr(Mission, champ) == oid, Mission.date_prevue == b.date_prevue,
                                   Mission.statut.in_(MISSION_OUVERTE))
        if sauf:
            st = st.where(Mission.id != sauf)
        autre = db.scalars(st).first()
        if autre:
            raise HTTPException(409, f"{nom} déjà affecté à la mission {autre.num} le {b.date_prevue:%d/%m/%Y}")


def _mission(db: Session, mid: int) -> Mission:
    return _get(db, Mission, mid, "Mission")


@router.get("/missions", response_model=list[MissionOut])
def missions(du: Optional[date] = None, au: Optional[date] = None, statut: str = "", q: str = "",
             _: User = Depends(LIRE), db: Session = Depends(get_db)):
    st = select(Mission).outerjoin(Dossier).order_by(Mission.date_prevue.desc(), Mission.id.desc())
    if du:
        st = st.where(Mission.date_prevue >= du)
    if au:
        st = st.where(Mission.date_prevue <= au)
    if statut:
        st = st.where(Mission.statut == statut)
    if q:
        like = f"%{q}%"
        st = st.where(or_(Mission.num.ilike(like), Mission.origine.ilike(like), Mission.destination.ilike(like),
                          Dossier.num.ilike(like)))
    return db.scalars(st).all()


@router.post("/missions", response_model=MissionOut, status_code=201)
def creer_mission(body: MissionIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    _verifier(db, body)
    m = Mission(**body.model_dump())
    db.add(m)
    db.flush()
    m.num = f"MIS-{body.date_prevue.year}-{m.id:04d}"
    audit(db, u, "mission", m.id, "création", f"{m.num} {m.type} {m.origine} -> {m.destination}")
    db.commit()
    return m


@router.get("/missions/{mid}", response_model=MissionOut)
def lire_mission(mid: int, _: User = Depends(LIRE), db: Session = Depends(get_db)):
    return _mission(db, mid)


@router.put("/missions/{mid}", response_model=MissionOut)
def modifier_mission(mid: int, body: MissionIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    m = _mission(db, mid)
    if m.statut != "Planifiée":
        raise HTTPException(409, f"Mission {m.statut.lower()} : seule une mission planifiée peut être modifiée")
    _verifier(db, body, sauf=m.id)
    for k, v in body.model_dump().items():
        setattr(m, k, v)
    audit(db, u, "mission", m.id, "modification", m.num)
    db.commit()
    return m


@router.post("/missions/{mid}/statut", response_model=MissionOut)
def statut_mission(mid: int, body: MissionStatutIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    m = _mission(db, mid)
    if body.to == "En cours":
        if m.statut != "Planifiée":
            raise HTTPException(409, f"Démarrage impossible depuis « {m.statut} »")
        if not (m.vehicule_id and m.chauffeur_id):
            raise HTTPException(422, "Affectez un véhicule et un chauffeur avant de démarrer la mission")
        m.debut = datetime.utcnow()
        if m.type == "Enlèvement" and m.conteneur and not m.conteneur.sortie:
            m.conteneur.sortie = date.today()  # sortie du port constatée au départ de l'enlèvement
            if not m.conteneur.arrivee:
                m.conteneur.arrivee = date.today()
    else:
        if m.statut not in MISSION_OUVERTE:
            raise HTTPException(409, f"Annulation impossible : mission déjà {m.statut.lower()}")
        if not body.motif.strip():
            raise HTTPException(422, "Indiquez le motif de l'annulation")
        m.incidents = [{"date": date.today().isoformat(), "type": "Annulation", "note": body.motif}, *m.incidents]
    audit(db, u, "mission", m.id, "statut", f"{m.statut} -> {body.to}")
    m.statut = body.to
    db.commit()
    return m


@router.post("/missions/{mid}/livrer", response_model=MissionOut)
def livrer(mid: int, body: LivraisonIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    m = _mission(db, mid)
    if m.statut != "En cours":
        raise HTTPException(409, "Seule une mission en cours peut être déclarée livrée")
    m.statut, m.fin = "Livrée", datetime.utcnow()
    m.receptionnaire, m.note_livraison, m.signature = body.receptionnaire, body.note, body.signature
    if m.type == "Retour vide" and m.conteneur and not m.conteneur.retour:
        m.conteneur.retour = date.today()
    audit(db, u, "mission", m.id, "livraison", f"Reçu par {body.receptionnaire}{' (signé)' if body.signature else ''}")
    db.commit()
    return m


@router.get("/missions/{mid}/signature")
def signature(mid: int, _: User = Depends(LIRE), db: Session = Depends(get_db)):
    m = _mission(db, mid)
    if not m.signature:
        raise HTTPException(404, "Aucune signature pour cette mission")
    return Response(base64.b64decode(m.signature.split(",", 1)[1]), media_type="image/png")


@router.post("/missions/{mid}/position", response_model=MissionOut)
def position(mid: int, body: PositionIn, _: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    """Dernière position connue (saisie par le chauffeur ou poussée par un boîtier GPS)."""
    m = _mission(db, mid)
    if m.statut != "En cours":
        raise HTTPException(409, "La position ne se met à jour que pendant une mission en cours")
    m.position = {"lat": body.lat, "lng": body.lng, "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z"}
    db.commit()
    return m


@router.post("/missions/{mid}/incidents", response_model=MissionOut, status_code=201)
def incident_mission(mid: int, body: MissionIncidentIn, u: User = Depends(ECRIRE), db: Session = Depends(get_db)):
    m = _mission(db, mid)
    m.incidents = [{"date": date.today().isoformat(), **body.model_dump()}, *m.incidents]
    audit(db, u, "mission", m.id, "incident", body.type)
    db.commit()
    return m


@router.get("/dossiers/{did}/missions", response_model=list[MissionOut])
def missions_dossier(d: Dossier = Depends(dossier_for), db: Session = Depends(get_db)):
    return db.scalars(select(Mission).where(Mission.dossier_id == d.id).order_by(Mission.date_prevue)).all()


# ---------- Synthèse ----------

@router.get("/operations/resume")
def resume(_: User = Depends(LIRE), db: Session = Depends(get_db)):
    today, limite = date.today(), date.today() + timedelta(days=ALERTE_JOURS)
    ms = db.scalars(select(Mission)).all()
    cts = db.scalars(select(Conteneur)).all()
    vs = db.scalars(select(Vehicule).where(Vehicule.actif)).all()
    chs = db.scalars(select(Chauffeur).where(Chauffeur.actif)).all()
    occupes = {m.vehicule_id for m in ms if m.statut == "En cours" or (m.statut == "Planifiée" and m.date_prevue == today)}
    alertes = [{"niveau": "ba", "texte": f"Mission {m.num} en retard (prévue le {m.date_prevue:%d/%m/%Y})"} for m in ms if m.en_retard]
    alertes += [{"niveau": "wa", "texte": f"Conteneur {c.numero} : {c.jours_magasinage} j de magasinage au-delà de la franchise"}
                for c in cts if c.statut == "Au port" and c.jours_magasinage]
    alertes += [{"niveau": "ba", "texte": f"Conteneur {c.numero} : vide non restitué, {c.jours_detention} j de détention"}
                for c in cts if c.statut == "Sorti" and c.jours_detention]
    for v in vs:
        for champ, lib in (("assurance_expire", "assurance"), ("visite_expire", "visite technique")):
            d = getattr(v, champ)
            if d and d <= limite:
                alertes.append({"niveau": "ba" if d < today else "wa",
                                "texte": f"Véhicule {v.immatriculation} : {lib} {'expirée' if d < today else 'à renouveler'} le {d:%d/%m/%Y}"})
    for c in chs:
        if c.permis_expire and c.permis_expire <= limite:
            alertes.append({"niveau": "ba" if c.permis_expire < today else "wa",
                            "texte": f"Chauffeur {c.nom} : permis {'expiré' if c.permis_expire < today else 'expire'} le {c.permis_expire:%d/%m/%Y}"})
    return {
        "missions_du_jour": sum(m.date_prevue == today and m.statut != "Annulée" for m in ms),
        "missions_en_cours": sum(m.statut == "En cours" for m in ms),
        "missions_en_retard": sum(m.en_retard for m in ms),
        "livrees_30j": sum(m.statut == "Livrée" and m.fin and m.fin.date() >= today - timedelta(days=30) for m in ms),
        "conteneurs_au_port": sum(c.statut == "Au port" for c in cts),
        "conteneurs_a_restituer": sum(c.statut == "Sorti" for c in cts),
        "jours_magasinage": sum(c.jours_magasinage for c in cts if c.statut == "Au port"),
        "vehicules_disponibles": sum(v.id not in occupes for v in vs),
        "vehicules_actifs": len(vs),
        "chauffeurs_actifs": len(chs),
        "alertes": alertes,
    }
