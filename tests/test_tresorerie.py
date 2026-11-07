"""Facturation : devis, avances, avoirs, règlements par mode, relances, balance âgée, exports comptables."""
import os
import uuid
import tempfile
from datetime import date, timedelta

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


def dossier(c, devise="GNF", delai=30):
    cli = c.post("/clients", json={"nom": f"Client {devise} {delai}", "nif": f"NIF-T-{uuid.uuid4().hex[:8]}", "devise": devise, "delai_paiement": delai}).json()
    return c.post("/dossiers", json=dict(type="Import", client_id=cli["id"], designation="Riz", code_sh="100630", colis=1,
                                         poids=1000, valeur=1000, devise="USD")).json()


def login(c, mail, role):
    c.post("/users", json={"email": mail, "nom": role, "role": role, "password": "MotDePasse!123"})
    return {"Authorization": "Bearer " + c.post("/auth/login", data={"username": mail, "password": "MotDePasse!123"}).json()["access_token"]}


def test_devis_vers_facture_en_devise(c):
    d = dossier(c, "USD")
    x = c.post(f"/dossiers/{d['id']}/devis", json={"lignes": [{"libelle": "Honoraires de transit", "montant": 860000},
                                                             {"libelle": "Transport", "montant": 1720000}], "validite_jours": 15})
    assert x.status_code == 201
    x = x.json()
    assert x["num"].startswith(f"DV-{TODAY.year}-") and x["devise"] == "USD" and x["total"] == 300  # 2 580 000 GNF / 8 600
    assert x["validite"] == str(TODAY + timedelta(days=15)) and x["statut"] == "Brouillon"
    assert c.post(f"/devis/{x['id']}/facturer", json={}).status_code == 409  # pas encore accepté
    assert c.post(f"/devis/{x['id']}/statut", json={"statut": "Envoyé"}).json()["statut"] == "Envoyé"
    assert c.post(f"/devis/{x['id']}/statut", json={"statut": "Envoyé"}).status_code == 409
    c.post(f"/devis/{x['id']}/statut", json={"statut": "Accepté"})
    f = c.post(f"/devis/{x['id']}/facturer", json={"refacturer_debours": True})
    assert f.status_code == 201
    f = f.json()
    assert f["devis_id"] == x["id"] and f["devise"] == "USD" and f["lignes"][0]["montant"] == 100
    assert f["lignes"][-1]["libelle"].startswith("Droits et taxes") and f["total"] > 300
    assert c.get("/devis", params={"statut": "Facturé"}).json()[0]["id"] == x["id"]
    assert c.post(f"/devis/{x['id']}/facturer", json={}).status_code == 409


def test_avance_avoir_reglements(c):
    d = dossier(c)
    a = c.post(f"/dossiers/{d['id']}/avances", json={"montant": 1000000, "mode": "Mobile money", "reference": "OM-5521"})
    assert a.status_code == 201 and a.json()["facture_id"] is None
    f = c.post(f"/dossiers/{d['id']}/facture", json={"lignes": [{"libelle": "Honoraires", "montant": 5000000}]}).json()
    assert f["paye"] == 1000000 and f["paiements"][0]["mode"] == "Avance" and f["statut"] == "Partielle"
    assert c.get(f"/dossiers/{d['id']}/avances").json()[0]["facture_id"] == f["id"]
    assert c.get("/factures/resume").json()["encaisse_mois"] >= 1000000  # l'avance compte à sa réception
    assert c.post(f"/dossiers/{d['id']}/avances", json={"montant": 5}).status_code == 409  # déjà facturé

    assert c.post(f"/factures/{f['id']}/avoirs", json={"montant": 5000000, "motif": "Trop"}).status_code == 422
    r = c.post(f"/factures/{f['id']}/avoirs", json={"montant": 500000, "motif": "Remise commerciale"}).json()
    assert r["total_avoirs"] == 500000 and r["solde"] == 3500000 and r["avoirs"][0]["num"].startswith("AV-")
    r = c.post(f"/factures/{f['id']}/paiements", json={"montant": 3500000, "mode": "Chèque", "reference": "CHQ 0042"}).json()
    assert r["solde"] == 0 and r["statut"] == "Soldée" and r["paiements"][-1]["reference"] == "CHQ 0042"
    assert c.post(f"/factures/{f['id']}/relance").status_code == 409
    assert c.get(f"/factures/{f['id']}").json()["num"] == f["num"]


def test_relances_et_balance(c):
    d = dossier(c, delai=30)
    f = c.post(f"/dossiers/{d['id']}/facture", json={"lignes": [{"libelle": "Transport", "montant": 2000000}]}).json()
    assert f["jours_retard"] == 0 and not any(x["facture_id"] == f["id"] for x in c.get("/factures-relances").json())
    from app.db import SessionLocal
    from app.models import Facture
    with SessionLocal() as db:  # facture émise il y a 75 jours, échue depuis 45
        x = db.get(Facture, f["id"])
        x.date_emission, x.echeance = TODAY - timedelta(days=75), TODAY - timedelta(days=45)
        db.commit()
    dues = {x["facture_id"]: x for x in c.get("/factures-relances").json()}
    assert dues[f["id"]]["niveau"] == "Rappel amiable" and "45 jours de retard" in dues[f["id"]]["lettre"]
    faites = c.post("/factures-relances").json()
    assert any(x["facture_id"] == f["id"] for x in faites)
    assert not any(x["facture_id"] == f["id"] for x in c.get("/factures-relances").json())  # 15 jours avant la suivante
    r = c.post(f"/factures/{f['id']}/relance").json()
    assert r["relances"] == 2 and r["niveau"] == "Deuxième relance" and r["derniere_relance"] == str(TODAY)
    s = c.get("/factures/resume").json()
    assert s["balance_agee"]["31_60"] >= 2000000 and s["en_retard"] >= 1 and s["creances"] >= 2000000
    assert c.get("/factures", params={"statut": "En retard"}).json()[0]["statut"] == "En retard"
    assert any(x["id"] == f["id"] for x in c.get("/factures", params={"statut": "ouvertes", "q": d["num"]}).json())


def test_exports(c):
    t = c.get("/factures/export.csv")
    assert t.status_code == 200 and t.text.startswith("﻿Facture;Date;Échéance") and "Remise" not in t.text
    v = c.get("/factures/export-ventes.csv").text
    assert "Avoir sur FA-" in v and "Remise commerciale" in v and ";-500000,00;" in v
    r = c.get("/factures/export-reglements.csv", params={"du": str(TODAY)}).text
    assert "CHQ 0042" in r and "Mobile" not in r.split("\n")[0]
    assert c.get("/factures/export.csv", params={"du": str(TODAY + timedelta(days=1))}).text.count("\n") == 1


def test_droits(c):
    com = login(c, "com.fact@a.gn", "Commercial")
    op = login(c, "op.fact@a.gn", "Agent opérationnel")
    d = dossier(c, "EUR")
    assert c.post(f"/dossiers/{d['id']}/devis", json={"lignes": [{"libelle": "Transit", "montant": 100000}]}, headers=com).status_code == 201
    assert c.get("/factures", headers=com).status_code == 200
    assert c.post(f"/dossiers/{d['id']}/facture", json={"lignes": [{"libelle": "X1", "montant": 1}]}, headers=com).status_code == 403
    assert c.get("/factures", headers=op).status_code == 403
    assert c.post(f"/dossiers/{d['id']}/devis", json={"lignes": []}).status_code == 422
