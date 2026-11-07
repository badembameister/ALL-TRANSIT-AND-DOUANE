"""Clients et partenaires : types et codes, doublons, recherche étendue, fiche, contacts, documents, droits."""
import os
import tempfile
import uuid
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
def cli(c):
    nif = f"NIF-P-{uuid.uuid4().hex[:6]}"
    r = c.post("/clients", json={"nom": "Kaloum Distribution", "nif": nif, "rc": "RCCM/GC-KAL/2019/B/1234", "adresse": "Avenue de la République",
                                 "ville": "Conakry", "telephone": "+224 622 00 00 00", "email": " Achats@Kaloum.GN ", "banque": "Ecobank Guinée",
                                 "compte_bancaire": "GN01 2345 6789", "plafond_credit": 1000000, "contact": "Fatoumata Camara"})
    assert r.status_code == 201
    return r.json() | {"_nif": nif}


def test_creation_types_codes(c, cli):
    assert cli["code"].startswith("C") and cli["type"] == "Client" and cli["email"] == "achats@kaloum.gn" and cli["actif"]
    assert c.post("/clients", json={"nom": "Doublon", "nif": cli["_nif"]}).status_code == 409
    t = c.post("/clients", json={"nom": "Trans-Sahel Logistique", "nif": cli["_nif"], "type": "Transporteur"})
    assert t.status_code == 201 and t.json()["code"].startswith("T")  # même NIF permis pour un autre type de partenaire
    assert c.post("/clients", json={"nom": "Mauvais mail", "email": "pas-un-mail"}).status_code == 422
    assert c.post("/clients", json={"nom": "Inconnu", "type": "Banque"}).status_code == 422
    types = {x["type"] for x in c.get("/clients", params={"type": "Transporteur"}).json()}
    assert types == {"Transporteur"}
    assert all(x["type"] == "Client" for x in c.get("/clients", params={"type": "Client"}).json())


def test_modification_et_inactivation(c, cli):
    body = {k: v for k, v in cli.items() if k not in {"id", "code", "created_at", "_nif"}}
    r = c.put(f"/clients/{cli['id']}", json={**body, "delai_paiement": 45, "actif": False})
    assert r.status_code == 200 and r.json()["delai_paiement"] == 45 and r.json()["code"] == cli["code"]
    assert not any(x["id"] == cli["id"] for x in c.get("/clients", params={"actifs": True}).json())
    c.put(f"/clients/{cli['id']}", json={**body, "actif": True})


def test_contacts(c, cli):
    url = f"/clients/{cli['id']}/contacts"
    fiche = c.get(f"/clients/{cli['id']}/fiche").json()
    assert fiche["contacts"][0]["nom"] == "Fatoumata Camara" and fiche["contacts"][0]["principal"]
    x = c.post(url, json={"nom": "Ibrahima Sow", "fonction": "Comptable", "email": "compta@kaloum.gn", "principal": True}).json()
    contacts = c.get(f"/clients/{cli['id']}/fiche").json()["contacts"]
    assert [y["principal"] for y in contacts] == [False, True]
    assert c.put(f"{url}/{x['id']}", json={"nom": "Ibrahima Sow", "fonction": "DAF", "principal": True}).json()["fonction"] == "DAF"
    assert c.delete(f"{url}/{x['id']}").status_code == 204
    assert c.get(f"/clients/{cli['id']}/fiche").json()["contacts"][0]["principal"] is True
    assert c.delete(f"{url}/9999").status_code == 404


def test_pieces(c, cli):
    url = f"/clients/{cli['id']}/pieces"
    bientot = str(TODAY + timedelta(days=10))
    p = c.post(url, data={"type": "Agrément", "expiration": bientot}, files={"fichier": ("agrement.pdf", b"%PDF agr")})
    assert p.status_code == 201 and p.json()["expiration"] == bientot and not p.json()["expire"]
    assert c.post(url, data={"type": "Passeport"}, files={"fichier": ("x.pdf", b"%PDF")}).status_code == 422
    assert c.post(url, data={"type": "Contrat", "expiration": "31/12/2026"}, files={"fichier": ("x.pdf", b"%PDF")}).status_code == 422
    assert c.get(f"{url}/{p.json()['id']}").content == b"%PDF agr"
    alertes = c.get(f"/clients/{cli['id']}/fiche").json()["alertes"]
    assert any("Agrément expire" in a for a in alertes)
    assert c.delete(f"{url}/{p.json()['id']}").status_code == 204
    assert c.get(f"{url}/{p.json()['id']}").status_code == 404


def test_fiche_historique_finances_et_recherche(c, cli):
    d = c.post("/dossiers", json=dict(type="Import", client_id=cli["id"], designation="Huile", code_sh="151190", colis=1, poids=1,
                                      valeur=1, devise="USD", transporteur="Trans-Sahel Logistique")).json()
    f = c.post(f"/dossiers/{d['id']}/facture", json={"lignes": [{"libelle": "Transit", "montant": 1500000}]}).json()
    from app.db import SessionLocal
    from app.models import Facture
    with SessionLocal() as db:
        x = db.get(Facture, f["id"])
        x.echeance = TODAY - timedelta(days=5)
        db.commit()
    fiche = c.get(f"/clients/{cli['id']}/fiche").json()
    s = fiche["stats"]
    assert s["dossiers"] == 1 and s["encours"] == 1500000 and s["factures_en_retard"] == 1 and s["ca_facture"] == 1500000
    assert any("plafond" in a for a in fiche["alertes"]) and fiche["dossiers"][0]["num"] == d["num"]
    trans = next(x for x in c.get("/clients", params={"type": "Transporteur"}).json() if x["nom"] == "Trans-Sahel Logistique")
    assert c.get(f"/clients/{trans['id']}/fiche").json()["dossiers"][0]["id"] == d["id"]  # historique côté transporteur
    for q in (d["num"], "kaloum", cli["code"], "RCCM/GC-KAL"):
        assert any(x["id"] == cli["id"] for x in c.get("/clients", params={"q": q}).json()), q


def test_droits(c, cli):
    c.post("/users", json={"email": "cpt.cli@a.gn", "nom": "Compta", "role": "Comptable", "password": "MotDePasse!123"})
    t = c.post("/auth/login", data={"username": "cpt.cli@a.gn", "password": "MotDePasse!123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    assert c.post("/clients", json={"nom": "Refusé"}, headers=h).status_code == 403
    assert c.get(f"/clients/{cli['id']}/fiche", headers=h).status_code == 200
    r = c.post(f"/clients/{cli['id']}/pieces", data={"type": "Attestation fiscale"}, files={"fichier": ("a.pdf", b"%PDF")}, headers=h)
    assert r.status_code == 201  # le comptable peut archiver les attestations
