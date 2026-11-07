"""Tableau de bord (cahier des charges, point 13) : indicateurs opérationnels, douaniers, financiers et de
rentabilité sur une période, tendance sur 12 mois, et alertes consolidées de tous les modules."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..fmt import milliers
from ..db import get_db
from ..deps import get_params
from ..customs import required_docs
from ..models import (Audit, Chauffeur, Client, Conteneur, Declaration, Dossier, Facture, Mission, PiecePartenaire, Transit, User,
                      Vehicule)
from ..security import require

router = APIRouter(tags=["Paramétrage et pilotage"])
VOIR = ("Responsable transit", "Commercial", "Direction", "Comptable")
OUVERTS = {"Ouvert", "En cours", "Bloqué"}
DEBOURS = "Droits et taxes avancés (débours)"


def _mois(d: date, n: int) -> date:
    """Premier jour du mois, décalé de n mois."""
    m = d.year * 12 + d.month - 1 + n
    return date(m // 12, m % 12 + 1, 1)


def _in(d, du: date, au: date) -> bool:
    if d is None:
        return False
    d = d.date() if isinstance(d, datetime) else d
    return du <= d <= au


@router.get("/pilotage")
def pilotage(du: Optional[date] = None, au: Optional[date] = None, u: User = Depends(require(*VOIR)),
             db: Session = Depends(get_db)):
    au = au or date.today()
    du = du or _mois(au, -11)
    if du > au:
        raise HTTPException(422, "La date de début doit précéder la date de fin")
    p = get_params(db)
    rate = lambda dev: Decimal(str(p["rates"].get(dev, 1)))  # noqa: E731
    today = date.today()

    dossiers = db.scalars(select(Dossier)).all()
    factures = db.scalars(select(Facture)).all()
    decls = db.scalars(select(Declaration)).all()
    transits = db.scalars(select(Transit)).all()
    missions = db.scalars(select(Mission)).all()
    conteneurs = db.scalars(select(Conteneur)).all()
    audits = db.scalars(select(Audit).where(Audit.entite.in_(["declaration", "facture"]),
                                            Audit.ts >= datetime.combine(du, time.min))).all()

    # ---------- Activité ----------
    par_statut = defaultdict(int)
    for d in dossiers:
        par_statut[d.statut] += 1
    ouverts_periode = [d for d in dossiers if _in(d.created_at, du, au)]
    par_type = defaultdict(int)
    for d in ouverts_periode:
        par_type[d.type] += 1
    actifs = [d for d in dossiers if d.statut in OUVERTS]
    manquantes = sum(len(set(required_docs(d.type)) - {x.type for x in d.documents}) for d in actifs)

    # ---------- Douane ----------
    bae = [x for x in decls if _in(x.bae_le, du, au) and x.delai_jours is not None]
    transmises = [x for x in decls if _in(x.transmise_le, du, au)]
    rejets = defaultdict(int)
    controles = 0
    for a in audits:
        if a.entite == "declaration" and a.action == "message douane" and _in(a.ts, du, au):
            if a.detail.endswith("-> Rejetée"):
                rejets[a.entite_id] += 1
            elif a.detail.endswith("-> Contrôle"):
                controles += 1
    premier_ok = [x for x in transmises if not rejets.get(x.dossier_id)]

    # ---------- Transit et opérations ----------
    inc_transit = [i for t in transits for i in (t.incidents or []) if _in(date.fromisoformat(i["date"]), du, au)]
    inc_missions = [i for m in missions for i in (m.incidents or []) if i.get("type") != "Annulation"
                    and _in(date.fromisoformat(i["date"]), du, au)]

    # ---------- Finance ----------
    fp = [f for f in factures if _in(f.date_emission, du, au)]
    ca_total = sum((f.total * rate(f.devise) for f in fp), Decimal(0))
    debours = sum((x.montant * rate(f.devise) for f in fp for x in f.lignes if x.libelle == DEBOURS), Decimal(0))
    par_client, par_prest, par_agent = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal)
    auteur = {a.detail.split(" ")[0]: a.utilisateur for a in audits if a.entite == "facture" and a.action == "génération"}
    for f in fp:
        v = f.total * rate(f.devise)
        par_client[f.client_nom] += v
        par_agent[auteur.get(f.num, "non tracé")] += v
        for x in f.lignes:
            par_prest["Débours (droits et taxes)" if x.libelle == DEBOURS else x.libelle] += x.montant * rate(f.devise)
    encours = [f for f in factures if f.solde > 0]
    retard = [f for f in encours if f.jours_retard > 0]

    # ---------- Rentabilité (dossiers facturés sur la période ; débours exclus du chiffre d'affaires et des coûts) ----------
    rent = []
    for f in fp:
        d = f.dossier
        prod = f.total * rate(f.devise) - sum((x.montant * rate(f.devise) for x in f.lignes if x.libelle == DEBOURS), Decimal(0))
        couts = sum((c.montant * rate(c.devise) for c in d.couts if c.categorie != "Droits et taxes"), Decimal(0))
        rent.append({"dossier_id": d.id, "num": d.num, "client": d.client.nom, "transporteur": d.transporteur or "Non renseigné",
                     "produits": prod, "couts": couts, "marge": prod - couts})
    def agreger(cle):  # noqa: E306
        acc = defaultdict(lambda: [Decimal(0), Decimal(0), 0])
        for r in rent:
            acc[r[cle]][0] += r["produits"]
            acc[r[cle]][1] += r["marge"]
            acc[r[cle]][2] += 1
        return sorted(({"nom": k, "produits": float(v[0]), "marge": float(v[1]), "dossiers": v[2],
                        "taux": round(float(v[1] / v[0] * 100), 1) if v[0] else None} for k, v in acc.items()),
                      key=lambda x: -x["marge"])
    rent_tri = sorted(rent, key=lambda r: r["marge"])
    rf = lambda r: {**r, "produits": float(r["produits"]), "couts": float(r["couts"]), "marge": float(r["marge"]),  # noqa: E731
                    "taux": round(float(r["marge"] / r["produits"] * 100), 1) if r["produits"] else None}

    # ---------- Tendance sur 12 mois (indépendante de la période) ----------
    debut = _mois(today, -11)
    tendance = []
    for i in range(12):
        m0, m1 = _mois(debut, i), _mois(debut, i + 1) - timedelta(days=1)
        tendance.append({"mois": m0.isoformat()[:7],
                         "ca": float(sum((f.total * rate(f.devise) for f in factures if m0 <= f.date_emission <= m1), Decimal(0))),
                         "dossiers": sum(1 for d in dossiers if d.created_at and m0 <= d.created_at.date() <= m1)})

    # ---------- Alertes consolidées ----------
    al = []
    def a(niveau, module, texte, lien=None):  # noqa: E306
        al.append({"niveau": niveau, "module": module, "texte": texte, "lien": lien})
    for t in transits:
        if t.en_retard:
            a("ba", "Transit", f"Transit {t.num or t.dossier_num} : délai de route dépassé (échéance {t.echeance:%d/%m/%Y})", {"vue": "transit", "id": t.id})
        if t.scelle_casse and t.statut != "Apurée":
            a("ba", "Transit", f"Transit {t.num or t.dossier_num} : scellé cassé signalé", {"vue": "transit", "id": t.id})
    for x in decls:
        if (x.attente_jours or 0) > 3:
            a("wa", "Douane", f"Déclaration {x.ref} sans bon à enlever depuis {x.attente_jours} jours", {"vue": "dossier", "id": x.dossier_id, "onglet": "douane"})
        if x.statut in {"Acceptée", "Contrôle"} and (x.montant_liquide or 0) > 0 and not x.quittance_ref:
            a("wa", "Douane", f"Déclaration {x.ref} : quittance des droits à payer", {"vue": "dossier", "id": x.dossier_id, "onglet": "douane"})
    for d in dossiers:
        if d.statut == "Bloqué":
            a("ba", "Dossiers", f"Dossier {d.num} bloqué", {"vue": "dossier", "id": d.id})
        elif d.statut in OUVERTS and d.completude < 100:
            a("wa", "Dossiers", f"Dossier {d.num} : documents manquants ({d.completude} % complet)", {"vue": "dossier", "id": d.id, "onglet": "docs"})
    for m in missions:
        if m.en_retard:
            a("ba", "Opérations", f"Mission {m.num} en retard (prévue le {m.date_prevue:%d/%m/%Y})", {"vue": "ops"})
    for c in conteneurs:
        if c.statut == "Au port" and c.jours_magasinage:
            a("wa", "Opérations", f"Conteneur {c.numero} : {c.jours_magasinage} j de magasinage hors franchise", {"vue": "ops"})
        if c.statut == "Sorti" and c.jours_detention:
            a("ba", "Opérations", f"Conteneur {c.numero} : vide non restitué, {c.jours_detention} j de détention", {"vue": "ops"})
    limite = today + timedelta(days=30)
    for v in db.scalars(select(Vehicule).where(Vehicule.actif)).all():
        for champ, lib in (("assurance_expire", "assurance"), ("visite_expire", "visite technique")):
            dt = getattr(v, champ)
            if dt and dt <= limite:
                a("ba" if dt < today else "wa", "Opérations", f"Véhicule {v.immatriculation} : {lib} {'expirée' if dt < today else 'à renouveler'} le {dt:%d/%m/%Y}", {"vue": "ops"})
    for ch in db.scalars(select(Chauffeur).where(Chauffeur.actif)).all():
        if ch.permis_expire and ch.permis_expire <= limite:
            a("ba" if ch.permis_expire < today else "wa", "Opérations", f"Chauffeur {ch.nom} : permis {'expiré' if ch.permis_expire < today else 'à renouveler'} le {ch.permis_expire:%d/%m/%Y}", {"vue": "ops"})
    for f in retard:
        a("ba" if f.jours_retard > 30 else "wa", "Facturation", f"Facture {f.num} ({f.client_nom}) : {f.jours_retard} j de retard, reste {milliers(f.solde)} {f.devise}",
          {"vue": "facture", "id": f.id})
    for pc in db.scalars(select(PiecePartenaire).where(PiecePartenaire.expiration.is_not(None), PiecePartenaire.expiration <= limite)).all():
        a("ba" if pc.expire else "wa", "Clients", f"{pc.type} de {_nom_client(db, pc.client_id)} {'expiré' if pc.expire else 'expire'} le {pc.expiration:%d/%m/%Y}",
          {"vue": "client", "id": pc.client_id})
    al.sort(key=lambda x: (x["niveau"] != "ba", x["module"]))

    top = lambda dct, n=8: [{"nom": k, "montant": float(v)} for k, v in sorted(dct.items(), key=lambda kv: -kv[1])[:n]]  # noqa: E731
    return {
        "periode": {"du": du, "au": au}, "devise_base": p["base"],
        "activite": {"par_statut": {s: par_statut.get(s, 0) for s in ["Ouvert", "En cours", "Bloqué", "Livré", "Clôturé"]},
                     "ouverts_periode": len(ouverts_periode), "par_type": dict(par_type),
                     "taux_complets": round(100 * sum(d.completude == 100 for d in actifs) / len(actifs)) if actifs else None,
                     "pieces_manquantes": manquantes},
        "douane": {"delai_moyen_jours": round(sum(x.delai_jours for x in bae) / len(bae), 1) if bae else None,
                   "bae": len(bae), "transmises": len(transmises),
                   "taux_premier_depot": round(100 * len(premier_ok) / len(transmises)) if transmises else None,
                   "rejets": sum(rejets.values()), "controles": controles,
                   "en_attente": sum(x.statut in {"Transmise", "Acceptée", "Contrôle"} for x in decls)},
        "transit": {"en_cours": sum(t.statut in {"En circulation", "Contrôlée", "Arrivée à destination"} for t in transits),
                    "non_apures_retard": sum(t.en_retard for t in transits),
                    "apures_periode": sum(_in(t.apurement, du, au) for t in transits), "incidents": len(inc_transit)},
        "operations": {"missions_livrees": sum(m.statut == "Livrée" and _in(m.fin, du, au) for m in missions),
                       "missions_en_retard": sum(m.en_retard for m in missions), "incidents": len(inc_missions),
                       "conteneurs_au_port": sum(c.statut == "Au port" for c in conteneurs),
                       "jours_magasinage": sum(c.jours_magasinage for c in conteneurs if c.statut == "Au port")},
        "finance": {"ca": float(ca_total), "ca_hors_debours": float(ca_total - debours), "factures": len(fp),
                    "creances": float(sum((f.solde * rate(f.devise) for f in encours), Decimal(0))),
                    "en_retard": len(retard), "montant_retard": float(sum((f.solde * rate(f.devise) for f in retard), Decimal(0))),
                    "par_client": top(par_client), "par_prestation": top(par_prest), "par_agent": top(par_agent)},
        "rentabilite": {"produits": float(sum((r["produits"] for r in rent), Decimal(0))),
                        "marge": float(sum((r["marge"] for r in rent), Decimal(0))),
                        "par_client": agreger("client")[:8], "par_transporteur": agreger("transporteur")[:8],
                        "meilleurs": [rf(r) for r in rent_tri[::-1][:5]], "moins_bons": [rf(r) for r in rent_tri[:5] if r["marge"] < r["produits"] * Decimal("0.1")]},
        "tendance": tendance,
        "alertes": al[:200],
    }


def _nom_client(db: Session, cid: int) -> str:
    c = db.get(Client, cid)
    return c.nom if c else "?"
