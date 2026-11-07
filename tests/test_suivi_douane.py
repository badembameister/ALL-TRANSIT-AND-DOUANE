"""Module douane : liste, synthèse, dates et délai de dédouanement, liquidation figée, quittance, rejet."""
import os
import tempfile
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as cl:
        tok = cl.post("/auth/login", data={"username": "admin@alliance.local", "password": "ChangeMe!2026"}).json()
        cl.headers["Authorization"] = f"Bearer {tok['access_token']}"
        yield cl


def dossier_pret(c, type_="Import", sh="100630"):
    cli = c.post("/clients", json={"nom": "Importateur Douane", "nif": "NIF-DN"}).json()
    d = c.post("/dossiers", json=dict(type=type_, client_id=cli["id"], designation="Riz", code_sh=sh, colis=10, poids=1000,
                                      valeur=10000, devise="USD")).json()
    for t in (("facture", "packing") if type_ == "Export" else ("facture", "packing", "bl")):
        c.post(f"/dossiers/{d['id']}/documents", data={"type": t}, files={"fichier": (f"{t}.pdf", b"%PDF")})
    return d


def test_cycle_et_delai(c):
    d = dossier_pret(c)
    url = f"/dossiers/{d['id']}/declaration"
    x = c.post(url).json()
    assert x["created_at"] and x["montant_liquide"] is None and x["dossier_num"] == d["num"] and x["client_nom"] == "Importateur Douane"
    total = c.get(url + "/calcul").json()["liquidation"]["total"]
    x = c.post(url + "/transmettre").json()
    assert x["transmise_le"] and x["montant_liquide"] == total and x["attente_jours"] == 0
    assert c.post(url + "/quittance", json={"ref": "Q-1", "montant": 1}).status_code == 409  # pas encore acceptée
    x = c.post(url + "/messages", json={"statut": "Acceptée", "ref_douane": "C 4512"}).json()
    assert x["ref_douane"] == "C 4512" and x["reponse_le"] and "C 4512" in x["messages"][-1]["texte"]
    q = c.post(url + "/quittance", json={"ref": "QT-2026-0778", "montant": total + 1000}).json()
    assert q["quittance_ref"] == "QT-2026-0778" and "écart de 1 000" in q["messages"][-1]["texte"]
    assert c.post(url + "/quittance", json={"ref": "QT-2", "montant": 5}).status_code == 409
    couts = c.get(f"/dossiers/{d['id']}/couts").json()
    assert couts["couts"][0]["categorie"] == "Droits et taxes" and couts["total_couts"] == total + 1000

    from app.db import SessionLocal
    from app.models import Declaration
    with SessionLocal() as db:  # transmise il y a 2 jours
        y = db.get(Declaration, x["id"])
        y.transmise_le = datetime.utcnow() - timedelta(days=2)
        db.commit()
    x = c.post(url + "/messages", json={"statut": "Bon à enlever"}).json()
    assert x["statut"] == "Bon à enlever" and 1.9 <= x["delai_jours"] <= 2.1 and x["attente_jours"] is None
    r = c.get("/declarations/resume").json()
    assert r["bae_30j"] >= 1 and r["delai_moyen_jours"] is not None and r["liquide_30j"] >= total


def test_export_sans_quittance_et_rejet(c):
    d = dossier_pret(c, "Export", "080131")
    url = f"/dossiers/{d['id']}/declaration"
    c.post(url)
    x = c.post(url + "/transmettre").json()
    assert x["montant_liquide"] == 0
    c.post(url + "/messages", json={"statut": "Contrôle"})
    assert c.post(url + "/messages", json={"statut": "Rejetée"}).status_code == 422  # motif obligatoire
    x = c.post(url + "/messages", json={"statut": "Rejetée", "texte": "Valeur sous-déclarée"}).json()
    assert x["statut"] == "Rejetée" and x["attente_jours"] is None
    x = c.post(url + "/rouvrir").json()
    assert x["statut"] == "Brouillon" and x["transmise_le"] is None
    x = c.post(url + "/transmettre").json()
    c.post(url + "/messages", json={"statut": "Acceptée"})
    assert c.post(url + "/messages", json={"statut": "Bon à enlever"}).json()["statut"] == "Bon à enlever"  # export : pas de droits


def test_liste_et_filtres(c):
    d = dossier_pret(c)
    c.post(f"/dossiers/{d['id']}/declaration")
    tout = c.get("/declarations").json()
    assert any(x["dossier_id"] == d["id"] and x["statut"] == "Brouillon" for x in tout)
    assert all(x["statut"] == "Bon à enlever" for x in c.get("/declarations", params={"statut": "Bon à enlever"}).json())
    assert c.get("/declarations", params={"q": "QT-2026-0778"}).json()[0]["quittance_ref"] == "QT-2026-0778"
    assert c.get("/declarations", params={"q": d["num"]}).json()[0]["dossier_id"] == d["id"]
    assert c.get("/declarations/resume").json()["brouillons"] >= 1


def test_droits(c):
    c.post("/users", json={"email": "cpt.dn@a.gn", "nom": "Compta", "role": "Comptable", "password": "MotDePasse!123"})
    t = c.post("/auth/login", data={"username": "cpt.dn@a.gn", "password": "MotDePasse!123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    assert c.get("/declarations", headers=h).status_code == 200
    d = dossier_pret(c)
    assert c.post(f"/dossiers/{d['id']}/declaration", headers=h).status_code == 403
