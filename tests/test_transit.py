"""Module transit : déclaration complète, bureaux de passage, contrôles de départ, rejet, apurement, échanges douane."""
import os
import tempfile
from datetime import date, timedelta

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


def nouveau_dossier(c, **extra):
    cli = c.post("/clients", json={"nom": "Atlantic Mining Supplies", "nif": "NIF-TR"}).json()
    return c.post("/dossiers", json=dict(type="Transit international", client_id=cli["id"], designation="Pièces d'engins",
                                         code_sh="843149", colis=12, poids=18500, valeur=90000, devise="EUR",
                                         fournisseur="Bergbau GmbH", transporteur="Trans-Sahel", **extra)).json()


def test_cycle_complet(c):
    d = nouveau_dossier(c)
    url = f"/dossiers/{d['id']}/transit"
    body = {"bureau_depart": "Conakry Port", "bureau_destination": "Bamako Route", "bureaux_passage": ["Mamou", " Kouremalé "],
            "garantie_montant": 25000000, "delai_jours": 10}
    t = c.post(url, json=body)
    assert t.status_code == 201
    t = t.json()
    assert t["num"].startswith(f"TR-{date.today().year}-") and t["statut"] == "En préparation"
    assert t["expediteur"] == "Bergbau GmbH" and t["transporteur"] == "Trans-Sahel"  # repris du dossier
    assert "12 colis" in t["marchandises"] and [p["bureau"] for p in t["passages"]] == ["Mamou", "Kouremalé"]
    assert t["dossier_num"] == d["num"] and t["client_nom"] == "Atlantic Mining Supplies"
    assert c.post(url, json=body).status_code == 409

    for s in ("Déposée", "Acceptée"):
        t = c.post(url + "/transition", json={"to": s, "ref_douane": "T1-GN-2026-778"}).json()
    assert t["ref_douane"] == "T1-GN-2026-778"
    assert [m["sens"] for m in t["messages"]] == ["interne", "envoi", "réception"]
    assert c.put(url, json=body).status_code == 409  # plus modifiable après acceptation

    # Départ refusé tant que véhicule, scellé et garantie manquent
    r = c.post(url + "/transition", json={"to": "En circulation"})
    assert r.status_code == 422 and "scellé" in r.json()["detail"]
    t = c.get(url).json()
    assert t["statut"] == "Acceptée"


def test_rejet_correction_et_apurement(c):
    d = nouveau_dossier(c)
    url = f"/dossiers/{d['id']}/transit"
    v = c.post("/vehicules", json={"immatriculation": "RC 9001 TR", "transporteur": "Sahel Trucks"}).json()
    ch = c.post("/chauffeurs", json={"nom": "Ousmane Keita"}).json()
    body = {"bureau_depart": "Conakry Port", "bureau_destination": "Bamako Route", "bureaux_passage": ["Mamou"],
            "vehicule_id": v["id"], "chauffeur_id": ch["id"], "scelle": "GN-12345, GN-12346", "garantie": "Caution bancaire BICIGUI"}
    t = c.post(url, json=body).json()
    assert t["vehicule"] == "RC 9001 TR" and t["chauffeur_nom"] == "Ousmane Keita"

    assert c.post(url + "/transition", json={"to": "Rejetée"}).status_code == 409  # pas avant dépôt
    c.post(url + "/transition", json={"to": "Déposée"})
    assert c.post(url + "/transition", json={"to": "Rejetée"}).status_code == 422  # motif obligatoire
    t = c.post(url + "/transition", json={"to": "Rejetée", "motif": "Poids incohérent avec le manifeste"}).json()
    assert t["statut"] == "Rejetée" and "Poids incohérent" in t["messages"][-1]["texte"]
    t = c.put(url, json={**body, "delai_jours": 5}).json()  # correction après rejet
    assert t["delai_jours"] == 5
    for s in ("En préparation", "Déposée", "Acceptée", "En circulation"):
        t = c.post(url + "/transition", json={"to": s}).json()
    assert t["statut"] == "En circulation" and t["depart"] == str(date.today())
    assert t["echeance"] == str(date.today() + timedelta(days=5))

    # Bureaux de passage
    assert c.post(url + "/passages", json={"bureau": "Kindia"}).status_code == 404
    assert c.post(url + "/transition", json={"to": "Arrivée à destination"}).status_code == 200
    r = c.post(url + "/transition", json={"to": "Apurée"})
    assert r.status_code == 422 and "Mamou" in r.json()["detail"]
    assert c.post(url + "/passages", json={"bureau": "mamou"}).status_code == 200  # régularisation après l'arrivée
    assert c.post(url + "/transition", json={"to": "Apurée"}).json()["statut"] == "Apurée"
    assert c.post(url + "/passages", json={"bureau": "mamou"}).status_code == 409  # plus rien après l'apurement

    # Incident scellé cassé : alerte
    assert c.post(url + "/incidents", json={"type": "Scellé cassé", "note": "Scellé GN-12346 rompu"}).status_code == 201
    assert any(x["id"] == t["id"] for x in c.get("/transits", params={"alerte": True}).json())
    assert c.post(url + "/messages", json={"sens": "réception", "texte": "Visite de la brigade mobile"}).status_code == 201


def test_passage_puis_apurement(c):
    d = nouveau_dossier(c)
    url = f"/dossiers/{d['id']}/transit"
    c.post(url, json={"bureau_depart": "Conakry Port", "bureau_destination": "Frontière Sierra Leone",
                      "bureaux_passage": ["Forécariah"], "vehicule": "RC 4", "scelle": "S-9", "garantie": "Caution"})
    for s in ("Déposée", "Acceptée", "En circulation"):
        c.post(url + "/transition", json={"to": s})
    t = c.post(url + "/passages", json={"bureau": "forécariah"}).json()
    assert t["passages"][0]["date"] == str(date.today())
    assert c.post(url + "/passages", json={"bureau": "Forécariah"}).status_code == 409
    for s in ("Contrôlée", "Arrivée à destination", "Apurée"):
        t = c.post(url + "/transition", json={"to": s, "motif": "Pesage"}).json()
    assert t["statut"] == "Apurée" and t["arrivee"] and t["apurement"] == str(date.today())
    assert c.post(url + "/transition", json={"to": "Rejetée", "motif": "x"}).status_code == 409
    r = c.get("/transits/resume").json()
    assert r["apures_30j"] >= 1
    assert all(x["statut"] in {"En circulation", "Contrôlée", "Arrivée à destination"} for x in c.get("/transits", params={"statut": "ouverts"}).json())


def test_retard(c):
    d = nouveau_dossier(c)
    url = f"/dossiers/{d['id']}/transit"
    c.post(url, json={"bureau_depart": "Conakry Port", "bureau_destination": "Bamako", "vehicule": "RC 5", "scelle": "S",
                      "garantie": "Caution", "delai_jours": 1})
    for s in ("Déposée", "Acceptée", "En circulation"):
        c.post(url + "/transition", json={"to": s})
    # Simule un départ ancien
    from app.db import SessionLocal
    from app.models import Transit
    with SessionLocal() as db:
        t = db.query(Transit).filter_by(dossier_id=d["id"]).one()
        t.depart = date.today() - timedelta(days=3)
        db.commit()
    assert c.get(url).json()["en_retard"] is True
    assert c.get("/transits/resume").json()["en_retard"] >= 1


def test_droits(c):
    c.post("/users", json={"email": "decl.tr@a.gn", "nom": "Déclarant", "role": "Déclarant en douane", "password": "MotDePasse!123"})
    tok = c.post("/auth/login", data={"username": "decl.tr@a.gn", "password": "MotDePasse!123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    d = nouveau_dossier(c)
    assert c.post(f"/dossiers/{d['id']}/transit", json={"bureau_depart": "AA", "bureau_destination": "BB"}, headers=h).status_code == 403
    assert c.get("/transits", headers=h).status_code == 200
