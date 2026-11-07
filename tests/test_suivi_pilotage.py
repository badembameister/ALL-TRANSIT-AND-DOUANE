"""Tableau de bord : indicateurs du point 13 sur une période, rentabilité, tendance, alertes consolidées, droits."""
import os
import tempfile
import uuid
from datetime import date, datetime, timedelta

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

TODAY = date.today()


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as cl:
        tok = cl.post("/auth/login", data={"username": "admin@alliance.local", "password": "ChangeMe!2026"}).json()
        cl.headers["Authorization"] = f"Bearer {tok['access_token']}"
        yield cl


@pytest.fixture(scope="module")
def scenario(c):
    cli = c.post("/clients", json={"nom": "Pilotage Mines SA", "nif": f"NIF-{uuid.uuid4().hex[:8]}"}).json()
    d = c.post("/dossiers", json=dict(type="Transit international", client_id=cli["id"], designation="Pièces", code_sh="843149",
                                      colis=5, poids=5000, valeur=10000, devise="USD", transporteur="Camions du Fouta")).json()
    for t in ("facture", "packing", "cmr"):
        c.post(f"/dossiers/{d['id']}/documents", data={"type": t}, files={"fichier": (f"{t}.pdf", b"%PDF")})
    url = f"/dossiers/{d['id']}/declaration"
    c.post(url)
    c.post(url + "/transmettre")
    c.post(url + "/messages", json={"statut": "Rejetée", "texte": "Valeur à justifier"})
    c.post(url + "/rouvrir")
    total = c.post(url + "/transmettre").json()["montant_liquide"]
    c.post(url + "/messages", json={"statut": "Acceptée"})
    c.post(url + "/quittance", json={"ref": f"Q-{uuid.uuid4().hex[:6]}", "montant": total})
    from app.db import SessionLocal
    from app.models import Declaration
    with SessionLocal() as db:  # transmission il y a 3 jours
        x = db.query(Declaration).filter_by(dossier_id=d["id"]).one()
        x.transmise_le = datetime.utcnow() - timedelta(days=3)
        db.commit()
    c.post(url + "/messages", json={"statut": "Bon à enlever"})
    c.post(f"/dossiers/{d['id']}/couts", json={"categorie": "Transport", "libelle": "Camion Conakry-Bamako", "montant": 4000000})
    f = c.post(f"/dossiers/{d['id']}/facture", json={"lignes": [{"libelle": "Honoraires de transit", "montant": 3000000},
                                                                 {"libelle": "Transport", "montant": 5000000}], "refacturer_debours": True}).json()
    # Deuxième dossier : bloqué, incomplet, avec un transit en retard
    d2 = c.post("/dossiers", json=dict(type="Transit national", client_id=cli["id"], designation="Ciment", code_sh="252329",
                                       colis=1, poids=1, valeur=1, devise="USD")).json()
    c.patch(f"/dossiers/{d2['id']}/statut", json={"statut": "Bloqué"})
    c.post(f"/dossiers/{d2['id']}/transit", json={"bureau_depart": "Conakry", "bureau_destination": "Kankan", "vehicule": "RC 1",
                                                  "scelle": "S1", "garantie": "Caution", "delai_jours": 2})
    for s in ("Déposée", "Acceptée", "En circulation"):
        c.post(f"/dossiers/{d2['id']}/transit/transition", json={"to": s})
    from app.models import Facture, Transit
    with SessionLocal() as db:
        db.query(Transit).filter_by(dossier_id=d2["id"]).one().depart = TODAY - timedelta(days=5)
        db.get(Facture, f["id"]).echeance = TODAY - timedelta(days=40)
        db.commit()
    return {"d": d, "d2": d2, "f": f, "total": total, "cli": cli}


def test_indicateurs(c, scenario):
    r = c.get("/pilotage").json()
    assert r["periode"]["au"] == str(TODAY) and r["devise_base"] == "GNF"
    assert r["activite"]["par_statut"]["Bloqué"] >= 1 and r["activite"]["ouverts_periode"] >= 2
    assert r["activite"]["pieces_manquantes"] >= 3  # dossier 2 : facture, packing, CMR
    dn = r["douane"]
    assert dn["rejets"] >= 1 and dn["bae"] >= 1 and 0 < dn["delai_moyen_jours"] < 30
    assert dn["taux_premier_depot"] is not None and dn["taux_premier_depot"] < 100  # le rejet compte
    assert r["transit"]["non_apures_retard"] >= 1
    fi = r["finance"]
    assert fi["ca"] >= 8000000 + scenario["total"] and fi["ca_hors_debours"] <= fi["ca"] - scenario["total"] + 1
    assert any(x["nom"] == "Pilotage Mines SA" for x in fi["par_client"])
    assert any(x["nom"] == "Débours (droits et taxes)" for x in fi["par_prestation"])
    assert any(x["nom"] == "admin@alliance.local" for x in fi["par_agent"])
    assert fi["en_retard"] >= 1 and len(r["tendance"]) == 12 and r["tendance"][-1]["mois"] == TODAY.isoformat()[:7]


def test_rentabilite(c, scenario):
    r = c.get("/pilotage").json()["rentabilite"]
    mien = next(x for x in r["meilleurs"] + r["moins_bons"] if x["dossier_id"] == scenario["d"]["id"])
    assert mien["produits"] == 8000000 and mien["couts"] == 4000000 and mien["marge"] == 4000000 and mien["taux"] == 50
    assert any(x["nom"] == "Camions du Fouta" and x["marge"] == 4000000 for x in r["par_transporteur"])


def test_alertes_et_periode(c, scenario):
    r = c.get("/pilotage").json()
    textes = " | ".join(a["texte"] for a in r["alertes"])
    assert f"Dossier {scenario['d2']['num']} bloqué" in textes and "délai de route dépassé" in textes
    assert f"Facture {scenario['f']['num']}" in textes and "40 j de retard, reste " in textes
    fac = next(a for a in r["alertes"] if scenario["f"]["num"] in a["texte"])
    assert fac["niveau"] == "ba" and fac["lien"] == {"vue": "facture", "id": scenario["f"]["id"]}
    assert r["alertes"][0]["niveau"] == "ba"  # les urgences d'abord
    vieux = c.get("/pilotage", params={"du": "2000-01-01", "au": "2000-12-31"}).json()
    assert vieux["finance"]["ca"] == 0 and vieux["douane"]["bae"] == 0 and vieux["activite"]["ouverts_periode"] == 0
    assert c.get("/pilotage", params={"du": "2026-12-01", "au": "2026-01-01"}).status_code == 422


def test_droits(c):
    for role, code in (("Direction", 200), ("Comptable", 200), ("Agent opérationnel", 403), ("Client", 403)):
        mail = f"{uuid.uuid4().hex[:6]}@a.gn"
        extra = {"client_id": 1} if role == "Client" else {}
        c.post("/users", json={"email": mail, "nom": role, "role": role, "password": "MotDePasse!123", **extra})
        t = c.post("/auth/login", data={"username": mail, "password": "MotDePasse!123"}).json()["access_token"]
        assert c.get("/pilotage", headers={"Authorization": f"Bearer {t}"}).status_code == code, role
