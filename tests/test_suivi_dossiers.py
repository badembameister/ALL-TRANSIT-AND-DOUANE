"""Module dossiers : modification, recherche étendue, étapes prévues/réelles, coûts et marge, journal."""
import os
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


@pytest.fixture(scope="module")
def dos(c):
    cli = c.post("/clients", json={"nom": "Guinée Ciments", "nif": "NIF-DOS", "devise": "GNF"}).json()
    body = dict(type="Import", client_id=cli["id"], ref="PO-77", designation="Clinker en vrac", code_sh="2523.10",
                colis=1, poids=30000, valeur=50000, devise="USD", incoterm="CFR", agent_douanier="Cabinet Diallo")
    d = c.post("/dossiers", json=body)
    assert d.status_code == 201
    return d.json() | {"_body": body}


def test_creation_et_modification(c, dos):
    assert dos["code_sh"] == "252310" and dos["incoterm"] == "CFR" and dos["client_nom"] == "Guinée Ciments"
    assert dos["transit_statut"] == "" and dos["facture_statut"] == ""
    assert c.post("/dossiers", json={**dos["_body"], "incoterm": "XXX"}).status_code == 422
    r = c.put(f"/dossiers/{dos['id']}", json={**dos["_body"], "poids": 31000, "lieu_livraison": "Usine de Kamsar"})
    assert r.status_code == 200 and float(r.json()["poids"]) == 31000 and r.json()["num"] == dos["num"]
    journal = c.get(f"/dossiers/{dos['id']}/journal").json()
    assert journal[0]["action"] == "modification" and "poids" in journal[0]["detail"]
    c.patch(f"/dossiers/{dos['id']}/statut", json={"statut": "Clôturé"})
    assert c.put(f"/dossiers/{dos['id']}", json=dos["_body"]).status_code == 409
    c.patch(f"/dossiers/{dos['id']}/statut", json={"statut": "En cours"})


def test_recherche_etendue(c, dos):
    c.post("/conteneurs", json={"numero": "MSKU9001235", "dossier_id": dos["id"], "arrivee": str(TODAY - timedelta(days=2))})
    c.post(f"/dossiers/{dos['id']}/declaration")
    for q in ("MSKU9001", "DUM-", "guinée ciments", "PO-77", "2523"):
        assert any(x["id"] == dos["id"] for x in c.get("/dossiers", params={"q": q}).json()), q
    assert c.get("/dossiers", params={"q": "ZZZZ"}).json() == []
    assert all(x["type"] == "Import" for x in c.get("/dossiers", params={"type": "Import"}).json())
    assert c.get("/dossiers", params={"q": "MSKU9001"}).json()[0]["declaration_statut"] == "Brouillon"


def test_jalons(c, dos):
    j = {x["cle"]: x for x in c.get(f"/dossiers/{dos['id']}/jalons").json()}
    assert "transit_depart" not in j  # pas d'étape transit pour un import
    assert j["ouverture"]["reelle"] == str(TODAY) and j["ouverture"]["automatique"]
    assert j["arrivee"]["reelle"] == str(TODAY - timedelta(days=2))  # date d'arrivée du conteneur
    r = c.put(f"/dossiers/{dos['id']}/jalons/bae", json={"prevue": str(TODAY - timedelta(days=1))})
    bae = {x["cle"]: x for x in r.json()}["bae"]
    assert bae["prevue"] == str(TODAY - timedelta(days=1)) and bae["reelle"] is None and bae["retard"] is True
    r = c.put(f"/dossiers/{dos['id']}/jalons/livraison", json={"prevue": str(TODAY), "reelle": str(TODAY + timedelta(days=2))})
    liv = {x["cle"]: x for x in r.json()}["livraison"]
    assert liv["ecart_jours"] == 2 and liv["retard"] and not liv["automatique"]
    assert c.put(f"/dossiers/{dos['id']}/jalons/inconnue", json={}).status_code == 404


def test_couts_et_marge(c, dos):
    url = f"/dossiers/{dos['id']}/couts"
    assert c.post(url, json={"categorie": "Transport", "libelle": "Camion Kamsar", "montant": 3000000}).status_code == 201
    k = c.post(url, json={"categorie": "Frais portuaires", "libelle": "Manutention port", "montant": 100, "devise": "USD"})
    assert k.status_code == 201
    assert c.post(url, json={"categorie": "Autre", "libelle": "Test", "montant": 1, "devise": "JPY"}).status_code == 422
    r = c.get(url).json()
    assert r["total_couts"] == 3000000 + 100 * 8600 and r["marge"] == -r["total_couts"] and r["taux_marge"] is None
    c.post(f"/dossiers/{dos['id']}/facture", json={"lignes": [{"libelle": "Honoraires", "montant": 5000000}]})
    r = c.get(url).json()
    assert r["facture"] == 5000000 and r["marge"] == 5000000 - 3860000 and r["taux_marge"] == 22.8
    assert c.delete(f"{url}/{k.json()['id']}").status_code == 204
    assert c.get(url).json()["total_couts"] == 3000000
    j = {x["cle"]: x for x in c.get(f"/dossiers/{dos['id']}/jalons").json()}
    assert j["facture"]["reelle"] == str(TODAY)


def test_droits(c, dos):
    c.post("/users", json={"email": "cli.dos@a.gn", "nom": "Client", "role": "Client", "password": "MotDePasse!123",
                           "client_id": dos["client_id"]})
    t = c.post("/auth/login", data={"username": "cli.dos@a.gn", "password": "MotDePasse!123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    assert c.get(f"/dossiers/{dos['id']}/couts", headers=h).status_code == 403  # marges réservées au personnel
    assert c.get(f"/dossiers/{dos['id']}/jalons", headers=h).status_code == 200
    assert c.put(f"/dossiers/{dos['id']}", json=dos["_body"], headers=h).status_code == 403
