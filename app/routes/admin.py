import csv
import io
import json
import os
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import LargeBinary, func, or_, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import Base, engine, get_db
from ..deps import get_params
from ..fichiers import cellule_csv
from ..gateway import SimulatedGateway, gateway
from ..models import Audit, Dossier, Facture, Param, User
from ..schemas import ParamsIn, ShImportIn, ShIn, SocieteIn
from ..security import STAFF, current_user, require

router = APIRouter(tags=["Paramétrage et pilotage"])


DEFAULT_SOCIETE = {"nom": "Alliance Transit", "slogan": "Transit, douane, logistique", "adresse": "", "ville": "Conakry",
                   "pays": "Guinée", "telephone": "", "email": "", "nif": "", "rc": "", "banque": "", "compte": "",
                   "pied_facture": "", "signature": "Service comptabilité"}


def get_societe(db: Session) -> dict:
    p = db.get(Param, "societe")
    return {**DEFAULT_SOCIETE, **(p.value if p else {})}


def _set_param(db: Session, key: str, value) -> None:
    p = db.get(Param, key)
    if p:
        p.value = value
    else:
        db.add(Param(key=key, value=value))


def _diff(avant: dict, apres: dict) -> str:
    """Résumé lisible des changements de paramètres, pour le journal d'audit."""
    out = []
    n = lambda v: f"{v:g}" if isinstance(v, (int, float)) else v  # noqa: E731  (8650.0 -> 8650)
    for dev in sorted(set(avant.get("rates", {})) | set(apres["rates"])):
        a, b = avant.get("rates", {}).get(dev), apres["rates"].get(dev)
        if a != b:
            out.append(f"taux {dev} : {n(a) if a is not None else 'nouveau'} -> {n(b) if b is not None else 'supprimé'}")
    for k, lib in (("base", "devise de base"), ("tva", "TVA"), ("dd0", "droit par défaut")):
        if avant.get(k) != apres[k]:
            out.append(f"{lib} : {n(avant.get(k))} -> {n(apres[k])}")
    for k, lib in (("taxes", "taxes"), ("reg", "régimes")):
        if avant.get(k) != apres[k]:
            out.append(f"{lib} modifiés")
    sh_a, sh_b = {x["c"]: x for x in avant.get("sh", [])}, {x["c"]: x for x in apres["sh"]}
    if sh_a != sh_b:
        out.append(f"codes SH : +{len(set(sh_b) - set(sh_a))} / -{len(set(sh_a) - set(sh_b))} / "
                   f"{sum(1 for c in set(sh_a) & set(sh_b) if sh_a[c] != sh_b[c])} modifiés")
    return "; ".join(out) or "aucun changement"


def _enregistrer(db: Session, u: User, value: dict) -> dict:
    avant = get_params(db)
    if value["rates"] != avant.get("rates"):
        value["rates_maj"] = date.today().isoformat()
    else:
        value["rates_maj"] = avant.get("rates_maj")
    _set_param(db, "douane", value)
    audit(db, u, "parametres", 0, "mise à jour", _diff(avant, value)[:2000])
    db.commit()
    return value


@router.get("/params")
def lire_params(_: User = Depends(require(*STAFF)), db: Session = Depends(get_db)):
    return get_params(db)


@router.put("/params")
def maj_params(body: ParamsIn, u: User = Depends(require()), db: Session = Depends(get_db)):
    return _enregistrer(db, u, body.model_dump())


@router.post("/params/sh/import")
def importer_sh(body: ShImportIn, u: User = Depends(require()), db: Session = Depends(get_db)):
    """Import du tarif : une ligne par code « code;libellé;droit %;accise % » (séparateur ; , ou tabulation)."""
    lignes, erreurs = [], []
    for i, brute in enumerate(body.csv.splitlines(), 1):
        if not brute.strip():
            continue
        sep = ";" if ";" in brute else "\t" if "\t" in brute else ","
        cols = [x.strip().strip('"') for x in brute.split(sep)]
        if i == 1 and not any(ch.isdigit() for ch in cols[0]):
            continue  # en-tête
        try:
            dd = float(cols[2].replace(",", ".").replace("%", "")) if len(cols) > 2 and cols[2] else 0.0
            ac = float(cols[3].replace(",", ".").replace("%", "")) if len(cols) > 3 and cols[3] else 0.0
            lignes.append(ShIn(c=cols[0], l=cols[1] if len(cols) > 1 else "", dd=dd, ac=ac).model_dump())
        except (ValueError, IndexError) as e:
            msg = e.errors()[0]["msg"].replace("Value error, ", "") if hasattr(e, "errors") else str(e)
            erreurs.append({"ligne": i, "contenu": brute[:80], "erreur": msg})
    if erreurs:
        raise HTTPException(422, {"message": f"{len(erreurs)} ligne(s) invalide(s), rien n'a été importé", "erreurs": erreurs[:50]})
    if not lignes:
        raise HTTPException(422, "Aucune ligne à importer")
    p = get_params(db)
    actuels = {} if body.mode == "remplacer" else {x["c"]: x for x in p["sh"]}
    nouveaux = sum(1 for x in lignes if x["c"] not in actuels)
    for x in lignes:
        actuels[x["c"]] = x
    value = ParamsIn(**{**p, "sh": sorted(actuels.values(), key=lambda x: x["c"])}).model_dump()
    _enregistrer(db, u, value)
    return {"importes": len(lignes), "nouveaux": nouveaux, "mis_a_jour": len(lignes) - nouveaux, "total": len(value["sh"])}


@router.get("/societe")
def lire_societe(_: User = Depends(current_user), db: Session = Depends(get_db)):
    """Coordonnées de la société (en-tête des documents), lisibles par tout utilisateur connecté, clients compris."""
    return get_societe(db)


@router.put("/societe")
def maj_societe(body: SocieteIn, u: User = Depends(require()), db: Session = Depends(get_db)):
    avant = get_societe(db)
    value = body.model_dump()
    _set_param(db, "societe", value)
    audit(db, u, "parametres", 0, "société", ", ".join(k for k in value if value[k] != avant.get(k)) or "aucun changement")
    db.commit()
    return value


def _audit_filtre(db: Session, q: str, entite: str, utilisateur: str, du: Optional[date], au: Optional[date], limit: int):
    st = select(Audit).order_by(Audit.id.desc())
    if entite:
        st = st.where(Audit.entite == entite)
    if utilisateur:
        st = st.where(Audit.utilisateur.ilike(f"%{utilisateur}%"))
    if du:
        st = st.where(Audit.ts >= datetime.combine(du, time.min))
    if au:
        st = st.where(Audit.ts <= datetime.combine(au, time.max))
    if q:
        st = st.where(or_(Audit.action.ilike(f"%{q}%"), Audit.detail.ilike(f"%{q}%")))
    return db.scalars(st.limit(min(limit, 5000))).all()


@router.get("/audit")
def journal(q: str = "", entite: str = "", utilisateur: str = "", du: Optional[date] = None, au: Optional[date] = None,
            limit: int = 200, _: User = Depends(require("Direction")), db: Session = Depends(get_db)):
    return [{"ts": a.ts, "utilisateur": a.utilisateur, "entite": a.entite, "entite_id": a.entite_id,
             "action": a.action, "detail": a.detail} for a in _audit_filtre(db, q, entite, utilisateur, du, au, limit)]


@router.get("/audit/export.csv")
def journal_csv(q: str = "", entite: str = "", utilisateur: str = "", du: Optional[date] = None, au: Optional[date] = None,
                _: User = Depends(require("Direction")), db: Session = Depends(get_db)):
    out = io.StringIO()
    out.write("\ufeff")
    w = csv.writer(out, delimiter=";")
    w.writerow(["Date", "Utilisateur", "Objet", "Identifiant", "Action", "Détail"])
    for a in _audit_filtre(db, q, entite, utilisateur, du, au, 5000):
        w.writerow([cellule_csv(v) for v in (a.ts.isoformat(sep=" ", timespec="seconds"), a.utilisateur, a.entite,
                                             a.entite_id, a.action, a.detail)])
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="journal-audit.csv"'})


@router.get("/admin/systeme")
def systeme(_: User = Depends(require()), db: Session = Depends(get_db)):
    """État de l'installation : volumes, base, intégrations et paramètres sensibles (sans aucun secret)."""
    volumes = {t.name: db.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables}
    p = get_params(db)
    return {
        "base_de_donnees": engine.dialect.name, "hebergement": "Vercel" if os.getenv("VERCEL") else "serveur",
        "volumes": volumes, "taux_maj": p.get("rates_maj"),
        "integrations": [
            {"nom": "Système douanier (SYDONIA World)", "etat": "simulé" if isinstance(gateway, SimulatedGateway) else "connecté",
             "detail": "Les transmissions renvoient une référence fictive SIM-… en attendant l'accès officiel."},
            {"nom": "E-mail", "etat": "non configuré", "detail": "Relances et notifications : texte généré, envoi manuel."},
            {"nom": "SMS / WhatsApp", "etat": "non configuré", "detail": "Passerelle à choisir (opérateur local ou agrégateur)."},
            {"nom": "GPS des véhicules", "etat": "prêt", "detail": "POST /api/missions/{id}/position accepte les positions d'un boîtier."},
        ],
        "sauvegardes": "Assurées par le fournisseur PostgreSQL (Neon) ; export JSON complémentaire disponible ci-dessous.",
    }


@router.get("/admin/export.json")
def export_donnees(u: User = Depends(require()), db: Session = Depends(get_db)):
    """Export des données métier (sans fichiers joints ni mots de passe), pour archivage."""
    data = {}
    for t in Base.metadata.sorted_tables:
        if t.name == "tentatives":  # échecs de connexion : données techniques, sans intérêt pour l'archivage
            continue
        cols = [c for c in t.columns if not isinstance(c.type, LargeBinary) and c.name not in ("pwd", "jeton_v")]
        data[t.name] = [dict(r._mapping) for r in db.execute(select(*cols))]
    audit(db, u, "parametres", 0, "export des données")
    db.commit()
    body = json.dumps({"exporte_le": datetime.utcnow().isoformat(timespec="seconds") + "Z", "tables": data},
                      default=str, ensure_ascii=False)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="alliance-export-{date.today()}.json"'})


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
