"""Module transport et suivi opérationnel : parc, conteneurs, missions, preuves de livraison."""
import base64
import os
import tempfile
from datetime import date, timedelta

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

TODAY = date.today()
PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as cl:
        tok = cl.post("/auth/login", data={"username": "admin@alliance.local", "password": "ChangeMe!2026"}).json()
        cl.headers["Authorization"] = f"Bearer {tok['access_token']}"
        yield cl


def login(c, mail, role, **extra):
    c.post("/users", json={"email": mail, "nom": role, "role": role, "password": "MotDePasse!123", **extra})
    t = c.post("/auth/login", data={"username": mail, "password": "MotDePasse!123"}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def dossier(c):
    cli = c.post("/clients", json={"nom": "Client Ops", "nif": "NIF-OPS", "devise": "GNF"}).json()
    d = c.post("/dossiers", json=dict(type="Import", client_id=cli["id"], designation="Ciment", code_sh="252329",
                                      colis=1, poids=28000, valeur=10000, devise="USD")).json()
    return d


def test_parc(c):
    v = c.post("/vehicules", json={"immatriculation": " rc 1234 ab ", "type": "Tracteur", "capacite_t": 40})
    assert v.status_code == 201 and v.json()["immatriculation"] == "RC 1234 AB"
    assert c.post("/vehicules", json={"immatriculation": "RC 1234 AB"}).status_code == 409
    assert c.post("/vehicules", json={"immatriculation": "XX 1", "type": "Avion"}).status_code == 422
    ch = c.post("/chauffeurs", json={"nom": "Mamadou Bah", "telephone": "+224 620 00 00 00",
                                     "permis_expire": str(TODAY + timedelta(days=10))})
    assert ch.status_code == 201
    alertes = [a["texte"] for a in c.get("/operations/resume").json()["alertes"]]
    assert any("Mamadou Bah" in a and "permis" in a for a in alertes)


def test_conteneurs(c, dossier):
    assert c.post("/conteneurs", json={"numero": "CSQU3054384"}).status_code == 422  # chiffre de contrôle faux
    arrivee = TODAY - timedelta(days=15)
    r = c.post("/conteneurs", json={"numero": "csqu 305438-3", "dossier_id": dossier["id"], "compagnie": "MSC",
                                    "arrivee": str(arrivee), "franchise_port": 10})
    assert r.status_code == 201
    k = r.json()
    assert k["numero"] == "CSQU3054383" and k["statut"] == "Au port" and k["jours_magasinage"] == 5
    assert k["dossier_num"] == dossier["num"]
    assert c.post("/conteneurs", json={"numero": "CSQU3054383"}).status_code == 409
    bad = {**k, "sortie": str(arrivee - timedelta(days=1))}
    assert c.put(f"/conteneurs/{k['id']}", json=bad).status_code == 422
    assert c.get("/conteneurs", params={"q": dossier["num"]}).json()[0]["id"] == k["id"]
    assert c.get("/conteneurs", params={"statut": "Au port"}).json()
    assert c.get(f"/dossiers/{dossier['id']}/conteneurs").json()[0]["numero"] == "CSQU3054383"
    resume = c.get("/operations/resume").json()
    assert resume["conteneurs_au_port"] == 1 and resume["jours_magasinage"] == 5


def test_mission_complete(c, dossier):
    v = c.get("/vehicules").json()[0]
    ch = c.get("/chauffeurs").json()[0]
    k = c.get("/conteneurs").json()[0]
    base = dict(type="Enlèvement", dossier_id=dossier["id"], conteneur_id=k["id"], origine="Port de Conakry",
                destination="Entrepôt client, Kagbelen", date_prevue=str(TODAY))
    m = c.post("/missions", json=base)
    assert m.status_code == 201
    m = m.json()
    assert m["num"].startswith(f"MIS-{TODAY.year}-") and m["statut"] == "Planifiée"

    # Démarrage refusé sans véhicule ni chauffeur
    assert c.post(f"/missions/{m['id']}/statut", json={"to": "En cours"}).status_code == 422
    m = c.put(f"/missions/{m['id']}", json={**base, "vehicule_id": v["id"], "chauffeur_id": ch["id"]}).json()
    assert m["vehicule_immat"] == v["immatriculation"] and m["chauffeur_nom"] == ch["nom"]

    # Double affectation le même jour
    autre = c.post("/missions", json={**base, "conteneur_id": None, "vehicule_id": v["id"]})
    assert autre.status_code == 409 and m["num"] in autre.json()["detail"]
    assert c.post("/missions", json={**base, "conteneur_id": None, "vehicule_id": v["id"],
                                     "date_prevue": str(TODAY + timedelta(days=1))}).status_code == 201

    # Livraison impossible avant le départ ; position seulement en cours
    assert c.post(f"/missions/{m['id']}/livrer", json={"receptionnaire": "M. Camara"}).status_code == 409
    assert c.post(f"/missions/{m['id']}/position", json={"lat": 9.5, "lng": -13.7}).status_code == 409
    m = c.post(f"/missions/{m['id']}/statut", json={"to": "En cours"}).json()
    assert m["statut"] == "En cours" and m["debut"]
    assert c.get(f"/conteneurs").json()[0]["statut"] == "Sorti"  # sortie du port enregistrée au départ
    assert c.put(f"/missions/{m['id']}", json=base).status_code == 409  # plus modifiable
    assert c.post(f"/missions/{m['id']}/position", json={"lat": 9.55, "lng": -13.67}).json()["position"]["lat"] == 9.55
    assert c.post(f"/missions/{m['id']}/position", json={"lat": 99, "lng": 0}).status_code == 422
    inc = c.post(f"/missions/{m['id']}/incidents", json={"type": "Contrôle routier", "note": "Péage Kilomètre 36"})
    assert inc.status_code == 201 and inc.json()["incidents"][0]["type"] == "Contrôle routier"

    # Preuve de livraison signée
    assert c.post(f"/missions/{m['id']}/livrer", json={"receptionnaire": "M. Camara", "signature": "data:text/plain,x"}).status_code == 422
    m = c.post(f"/missions/{m['id']}/livrer", json={"receptionnaire": "M. Camara", "note": "RAS", "signature": PNG}).json()
    assert m["statut"] == "Livrée" and m["signee"] and m["receptionnaire"] == "M. Camara"
    sig = c.get(f"/missions/{m['id']}/signature")
    assert sig.status_code == 200 and sig.headers["content-type"] == "image/png"
    assert c.post(f"/missions/{m['id']}/statut", json={"to": "Annulée", "motif": "x"}).status_code == 409
    assert c.get("/missions", params={"statut": "Livrée"}).json()[0]["id"] == m["id"]
    assert c.get(f"/dossiers/{dossier['id']}/missions").json()


def test_retour_vide_et_annulation(c):
    k = c.get("/conteneurs").json()[0]
    v, ch = c.get("/vehicules").json()[0], c.get("/chauffeurs").json()[0]
    j2 = str(TODAY + timedelta(days=2))
    m = c.post("/missions", json=dict(type="Retour vide", conteneur_id=k["id"], vehicule_id=v["id"], chauffeur_id=ch["id"],
                                      origine="Kagbelen", destination="Dépôt MSC", date_prevue=j2)).json()
    c.post(f"/missions/{m['id']}/statut", json={"to": "En cours"})
    c.post(f"/missions/{m['id']}/livrer", json={"receptionnaire": "Dépôt MSC"})
    assert c.get("/conteneurs").json()[0]["statut"] == "Restitué"

    x = c.post("/missions", json=dict(type="Livraison", origine="Entrepôt", destination="Client", date_prevue=str(TODAY - timedelta(days=3)))).json()
    assert x["en_retard"] is True
    assert c.get("/operations/resume").json()["missions_en_retard"] >= 1
    assert c.post(f"/missions/{x['id']}/statut", json={"to": "Annulée", "motif": " "}).status_code == 422
    x = c.post(f"/missions/{x['id']}/statut", json={"to": "Annulée", "motif": "Client absent"}).json()
    assert x["statut"] == "Annulée" and x["en_retard"] is False and x["incidents"][0]["type"] == "Annulation"


def test_droits_operations(c, dossier):
    agent = login(c, "ops@a.gn", "Agent opérationnel")
    compta = login(c, "cpt.ops@a.gn", "Comptable")
    client = login(c, "cli.ops@a.gn", "Client", client_id=dossier["client_id"])
    assert c.post("/chauffeurs", json={"nom": "Alpha Diallo"}, headers=agent).status_code == 201
    assert c.post("/chauffeurs", json={"nom": "Refusé"}, headers=compta).status_code == 403
    assert c.get("/missions", headers=compta).status_code == 200  # lecture pour tout le personnel
    assert c.get("/missions", headers=client).status_code == 403
    assert c.get(f"/dossiers/{dossier['id']}/missions", headers=client).status_code == 200  # ses propres dossiers
    assert c.get(f"/dossiers/{dossier['id']}/conteneurs", headers=client).json()
