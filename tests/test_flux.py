import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

DOSSIER = dict(type="Import", client_id=1, ref="PO-1", designation="Riz blanc", code_sh="100630", colis=800,
               poids=40000, valeur=28000, devise="USD", origine="Thaïlande", fret=12000000, assurance=1500000)


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as cl:
        tok = cl.post("/auth/login", data={"username": "admin@alliance.local", "password": "ChangeMe!2026"}).json()
        cl.headers["Authorization"] = f"Bearer {tok['access_token']}"
        yield cl


def test_flux_complet(c):
    assert c.post("/auth/login", data={"username": "admin@alliance.local", "password": "x"}).status_code == 401
    cli = c.post("/clients", json={"nom": "Sahel Négoce SA", "nif": "NIF-1", "devise": "GNF"})
    assert cli.status_code == 201 and cli.json()["code"] == "C0001"
    d = c.post("/dossiers", json=DOSSIER)
    assert d.status_code == 201
    did = d.json()["id"]
    assert d.json()["num"].startswith("IMP-") and d.json()["completude"] == 0

    # Liquidation : CIF = 28000*8600 + 12 000 000 + 1 500 000 = 254 300 000 ; droit 10 % (riz)
    calc = c.post(f"/dossiers/{did}/declaration").status_code == 201 and c.get(f"/dossiers/{did}/declaration/calcul").json()
    liq = calc["liquidation"]
    assert liq["valeur_cif"] == 254300000 and liq["droit_douane"]["montant"] == 25430000
    taxes = sum(t["montant"] for t in liq["autres_taxes"])  # 1 % + 0,5 % du CIF
    assert taxes == 3814500
    tva = round((254300000 + 25430000 + taxes) * 0.18)
    assert liq["tva"]["montant"] == tva and liq["total"] == 25430000 + taxes + tva

    # Transmission bloquée tant que les documents manquent
    r = c.post(f"/dossiers/{did}/declaration/transmettre")
    assert r.status_code == 422 and len(r.json()["detail"]["bloquants"]) == 3
    for t in ("facture", "packing", "bl"):
        up = c.post(f"/dossiers/{did}/documents", data={"type": t}, files={"fichier": (f"{t}.pdf", b"%PDF-1.4 test")})
        assert up.status_code == 201
        last = up.json()["id"]
    assert c.get(f"/documents/{last}/download").content == b"%PDF-1.4 test"
    assert c.get(f"/dossiers/{did}").json()["completude"] == 100
    assert c.post(f"/dossiers/{did}/documents", data={"type": "facture"}, files={"fichier": ("x.exe", b"MZ")}).status_code == 415
    assert c.post(f"/dossiers/{did}/declaration/transmettre").json()["statut"] == "Transmise"
    assert c.post(f"/dossiers/{did}/declaration/messages", json={"statut": "Bon à enlever"}).status_code == 409
    for s in ("Acceptée", "Bon à enlever"):
        assert c.post(f"/dossiers/{did}/declaration/messages", json={"statut": s}).json()["statut"] == s

    # Transit : machine à états
    assert c.post(f"/dossiers/{did}/transit", json={"bureau_depart": "Port de Conakry", "bureau_destination": "Frontière", "delai_jours": 7, "vehicule": "RC 1", "scelle": "S-1", "garantie": "Caution"}).status_code == 201
    assert c.post(f"/dossiers/{did}/transit/transition", json={"to": "Apurée"}).status_code == 409
    for s in ("Déposée", "Acceptée", "En circulation", "Arrivée à destination", "Apurée"):
        assert c.post(f"/dossiers/{did}/transit/transition", json={"to": s}).json()["statut"] == s
    assert c.post(f"/dossiers/{did}/transit/incidents", json={"type": "Retard", "note": "pluie"}).json()["incidents"][0]["type"] == "Retard"

    # Facturation en GNF avec refacturation des débours, puis règlements
    f = c.post(f"/dossiers/{did}/facture", json={"lignes": [{"libelle": "Honoraires", "montant": 2500000}], "refacturer_debours": True}).json()
    assert f["total"] == 2500000 + liq["total"] and f["statut"] == "Impayée"
    assert c.post(f"/factures/{f['id']}/paiements", json={"montant": f["total"] + 1}).status_code == 422
    assert c.post(f"/factures/{f['id']}/paiements", json={"montant": 1000000}).json()["statut"] == "Partielle"
    assert c.post(f"/factures/{f['id']}/paiements", json={"montant": f["total"] - 1000000}).json()["statut"] == "Payée"
    assert "Sahel Négoce SA" in c.get("/factures/export.csv").text
    assert c.get("/dashboard").json()["dossiers_ouverts"] == 1
    assert len(c.get(f"/dossiers/{did}/journal").json()) >= 10


def test_droits_par_role(c):
    c.post("/users", json={"email": "cpt@a.gn", "nom": "Compta", "role": "Comptable", "password": "MotDePasse!123"})
    c.post("/users", json={"email": "cli@a.gn", "nom": "Client", "role": "Client", "password": "MotDePasse!123", "client_id": 1})
    c.post("/clients", json={"nom": "Autre client", "nif": "N2"})
    c.post("/dossiers", json={**DOSSIER, "client_id": 2})

    def login(mail):
        t = c.post("/auth/login", data={"username": mail, "password": "MotDePasse!123"}).json()["access_token"]
        return {"Authorization": f"Bearer {t}"}

    compta, client = login("cpt@a.gn"), login("cli@a.gn")
    assert c.post("/dossiers", json=DOSSIER, headers=compta).status_code == 403
    assert c.get("/factures", headers=compta).status_code == 200
    mine = c.get("/dossiers", headers=client).json()
    assert mine and all(x["client_id"] == 1 for x in mine)
    assert c.get("/dossiers/2", headers=client).status_code == 404
    assert c.get("/factures", headers=client).status_code == 403
    assert c.get("/clients", headers=client).status_code == 403


def test_montage_vercel(c):
    from api.index import app as vercel_app
    v = TestClient(vercel_app)
    assert v.get("/api/health").json() == {"status": "ok"}
    r = v.post("/api/auth/login", data={"username": "admin@alliance.local", "password": "ChangeMe!2026"})
    assert r.status_code == 200 and r.json()["role"] == "Administrateur"


def test_gestion_utilisateurs(c):
    assert c.post("/users", json={"email": "x@a.gn", "nom": "X", "role": "Agent opérationnel", "password": "court"}).status_code == 422
    assert c.post("/users", json={"email": "x@a.gn", "nom": "X Y", "role": "Client", "password": "MotDePasse!123"}).status_code == 422
    u = c.post("/users", json={"email": " Agent@A.GN ", "nom": "Agent Un", "role": "Agent opérationnel", "password": "MotDePasse!123"})
    assert u.status_code == 201 and u.json()["email"] == "agent@a.gn" and u.json()["actif"] is True
    uid = u.json()["id"]
    assert c.post("/users", json={"email": "AGENT@a.gn", "nom": "Doublon", "role": "Agent opérationnel", "password": "MotDePasse!123"}).status_code == 409
    assert c.patch(f"/users/{uid}", json={"role": "Comptable"}).json()["role"] == "Comptable"
    me = c.get("/auth/me").json()["id"]
    assert c.patch(f"/users/{me}", json={"actif": False}).status_code == 422
    assert c.post(f"/users/{uid}/password", json={"password": "NouveauPass2026"}).status_code == 204
    ok = c.post("/auth/login", data={"username": "AGENT@a.gn", "password": "NouveauPass2026"})
    assert ok.status_code == 200
    h = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert c.get("/users", headers=h).status_code == 403
    assert c.post("/auth/change-password", json={"ancien": "faux", "nouveau": "Autre2026Pass"}, headers=h).status_code == 403
    assert c.post("/auth/change-password", json={"ancien": "NouveauPass2026", "nouveau": "Autre2026Pass"}, headers=h).status_code == 204
    assert c.patch(f"/users/{uid}", json={"actif": False}).json()["actif"] is False
    assert c.post("/auth/login", data={"username": "agent@a.gn", "password": "Autre2026Pass"}).status_code == 401
