"""Portail client : accueil, notifications traduites et lues, factures du client, dépôt de pièces, cloisonnement."""
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


def compte(c, client_id, role="Client"):
    mail = f"{uuid.uuid4().hex[:8]}@client.gn"
    body = {"email": mail, "nom": "Fatoumata Camara", "role": role, "password": "MotDePasse!123"}
    if client_id:
        body["client_id"] = client_id
    c.post("/users", json=body)
    t = c.post("/auth/login", data={"username": mail, "password": "MotDePasse!123"}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}, mail


@pytest.fixture(scope="module")
def monde(c):
    cli = c.post("/clients", json={"nom": "Portail Négoce", "nif": f"NIF-{uuid.uuid4().hex[:8]}"}).json()
    autre = c.post("/clients", json={"nom": "Concurrent SA", "nif": f"NIF-{uuid.uuid4().hex[:8]}"}).json()
    d = c.post("/dossiers", json=dict(type="Import", client_id=cli["id"], ref="PO-1", designation="Riz", code_sh="100630", colis=1,
                                      poids=1000, valeur=1000, devise="USD")).json()
    c.post(f"/dossiers/{d['id']}/documents", data={"type": "facture"}, files={"fichier": ("f.pdf", b"%PDF")})
    c.post(f"/dossiers/{d['id']}/declaration")
    c.put(f"/dossiers/{d['id']}/jalons/arrivee", json={"prevue": str(TODAY + timedelta(days=3))})
    v = c.post("/vehicules", json={"immatriculation": f"RC {uuid.uuid4().hex[:5]}"}).json()
    ch = c.post("/chauffeurs", json={"nom": "Alpha"}).json()
    m = c.post("/missions", json=dict(type="Livraison", dossier_id=d["id"], vehicule_id=v["id"], chauffeur_id=ch["id"],
                                      origine="Port de Conakry", destination="Entrepôt", date_prevue=str(TODAY + timedelta(days=1)))).json()
    c.post(f"/missions/{m['id']}/incidents", json={"type": "Retard", "note": "Embouteillage"})
    f = c.post(f"/dossiers/{d['id']}/facture", json={"lignes": [{"libelle": "Honoraires", "montant": 1000000}]}).json()
    c.post(f"/dossiers/{d['id']}/couts", json={"categorie": "Transport", "libelle": "Camion", "montant": 400000})
    d_autre = c.post("/dossiers", json=dict(type="Export", client_id=autre["id"], designation="Cajou", code_sh="080131", colis=1,
                                            poids=1, valeur=1, devise="EUR")).json()
    f_autre = c.post(f"/dossiers/{d_autre['id']}/facture", json={"lignes": [{"libelle": "Honoraires", "montant": 5}]}).json()
    h, mail = compte(c, cli["id"])
    return {"cli": cli, "d": d, "f": f, "m": m, "d_autre": d_autre, "f_autre": f_autre, "h": h, "mail": mail}


def test_accueil(c, monde):
    a = c.get("/portail/accueil", headers=monde["h"]).json()
    d = a["dossiers"][0]
    assert d["num"] == monde["d"]["num"] and d["pieces_manquantes"] == ["Packing list", "Connaissement / LTA"]
    assert d["prochaine_etape"] == {"libelle": "Arrivée des marchandises", "prevue": str(TODAY + timedelta(days=3))}
    assert d["douane"] == "Brouillon" and 0 < d["etapes_faites"] < d["etapes"]
    assert a["livraisons"][0]["num"] == monde["m"]["num"] and a["a_payer"][0]["num"] == monde["f"]["num"]
    assert a["a_payer"][0]["solde"] == 1000000 and "couts" not in str(a).lower()


def test_notifications(c, monde):
    h = monde["h"]
    n = c.get("/portail/notifications", headers=h).json()
    textes = [x["texte"] for x in n]
    num = monde["d"]["num"]
    assert f"Dossier {num} ouvert" in textes and f"{num} : document ajouté (Facture commerciale)" in textes
    assert f"{num} : transport planifié" in textes and f"{num} : incident de transport (retard)" in textes
    assert any("facture FA-" in t and "émise" in t for t in textes)
    assert not any("Camion" in t or "coût" in t.lower() or "étape" in t for t in textes)  # rien d'interne
    assert not any(monde["d_autre"]["num"] in t for t in textes)
    assert all(x["nouveau"] for x in n) and c.get("/portail/accueil", headers=h).json()["non_lues"] == len(n)
    assert c.post("/portail/notifications/vues", headers=h).status_code == 204
    assert c.get("/portail/accueil", headers=h).json()["non_lues"] == 0
    c.post(f"/dossiers/{monde['d']['id']}/declaration/transmettre")  # bloquée (pièces manquantes) : pas d'événement
    c.patch(f"/dossiers/{monde['d']['id']}/statut", json={"statut": "En cours"})
    n = c.get("/portail/notifications", headers=h).json()
    assert n[0]["texte"] == f"Dossier {num} : en cours" and n[0]["nouveau"] and not n[1]["nouveau"]


def test_factures(c, monde):
    h = monde["h"]
    fs = c.get("/portail/factures", headers=h).json()
    assert [f["id"] for f in fs] == [monde["f"]["id"]]
    assert c.get(f"/portail/factures/{monde['f']['id']}", headers=h).json()["total"] == 1000000
    assert c.get(f"/portail/factures/{monde['f_autre']['id']}", headers=h).status_code == 404
    assert c.get("/societe", headers=h).status_code == 200  # en-tête des factures imprimées
    assert c.get("/factures", headers=h).status_code == 403


def test_depot_par_le_client(c, monde):
    h, did = monde["h"], monde["d"]["id"]
    r = c.post(f"/dossiers/{did}/documents", data={"type": "packing"}, files={"fichier": ("pl.pdf", b"%PDF pl")}, headers=h)
    assert r.status_code == 201 and r.json()["depose_par"] == "Vous"
    assert c.post(f"/dossiers/{did}/documents", data={"type": "quittance"}, files={"fichier": ("q.pdf", b"%PDF")}, headers=h).status_code == 403
    assert c.post(f"/dossiers/{monde['d_autre']['id']}/documents", data={"type": "packing"}, files={"fichier": ("x.pdf", b"%PDF")}, headers=h).status_code == 404
    docs = {x["type"]: x["depose_par"] for x in c.get(f"/dossiers/{did}/documents", headers=h).json()}
    assert docs == {"facture": "Alliance Transit", "packing": "Vous"}  # pas d'adresse d'employé
    assert c.get(f"/dossiers/{did}/documents").json()[0]["depose_par"] == "admin@alliance.local"  # le personnel voit tout
    n = c.get("/portail/notifications", headers=h).json()
    assert n[0]["texte"].endswith("document ajouté (Packing list)")
    c.patch(f"/dossiers/{did}/statut", json={"statut": "Clôturé"})
    assert c.post(f"/dossiers/{did}/documents", data={"type": "bl"}, files={"fichier": ("b.pdf", b"%PDF")}, headers=h).status_code == 409
    c.patch(f"/dossiers/{did}/statut", json={"statut": "En cours"})


def test_acces(c, monde):
    staff, _ = compte(c, None, "Comptable")
    assert c.get("/portail/accueil", headers=staff).status_code == 403
    r = c.post("/users", json={"email": "orphelin@client.gn", "nom": "Sans client", "role": "Client", "password": "MotDePasse!123"})
    assert r.status_code == 422  # un compte client est toujours rattaché à un client
