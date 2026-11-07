"""Administration : validation des paramètres, historique des taux, société, import du tarif SH, journal d'audit,
état du système, export des données, droits."""
import os
import tempfile
from datetime import date

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


@pytest.fixture(scope="module")
def p0(c):
    return c.get("/params").json()


def test_validation_parametres(c, p0):
    for bad, mot in [({"rates": {**p0["rates"], "GNF": 2}}, "taux de 1"), ({"rates": {**p0["rates"], "USD": 0}}, "positif"),
                     ({"rates": {**p0["rates"], "DOLLAR": 1}}, "Code devise"), ({"reg": []}, "Régimes"),
                     ({"sh": p0["sh"] + [p0["sh"][0]]}, "en double"), ({"tva": 150}, "100"),
                     ({"taxes": p0["taxes"] + [p0["taxes"][0]]}, "même nom"), ({"sh": [{"c": "1", "l": "Trop court", "dd": 5}]}, "2 à 10")]:
        r = c.put("/params", json={**p0, **bad})
        assert r.status_code == 422 and mot in r.text, (bad, r.text[:200])
    assert c.get("/params").json()["rates"] == p0["rates"]  # rien n'a changé


def test_taux_et_journal(c, p0):
    r = c.put("/params", json={**p0, "rates": {**p0["rates"], "USD": 8650, "xof": 14.2}}).json()
    assert r["rates"]["XOF"] == 14.2 and r["rates_maj"] == str(date.today())
    j = c.get("/audit", params={"entite": "parametres", "q": "taux"}).json()
    assert "taux USD : 8600" in j[0]["detail"] and "-> 8650" in j[0]["detail"] and "XOF : nouveau" in j[0]["detail"]
    csv = c.get("/audit/export.csv", params={"entite": "parametres"}).text
    assert csv.startswith("﻿Date;Utilisateur;Objet") and "taux USD" in csv
    assert c.get("/audit", params={"du": "2000-01-01", "au": "2000-01-02"}).json() == []
    c.put("/params", json=p0)


def test_import_sh(c, p0):
    csv = "code;libellé;droit;accise\n1006.30;Riz semi-blanchi;10;0\n2523 29;Ciment Portland;20;\n87032310;Voitures 1500-3000 cm3;20,5;5\n"
    r = c.post("/params/sh/import", json={"csv": csv})
    assert r.status_code == 200 and r.json()["importes"] == 3
    sh = {x["c"]: x for x in c.get("/params").json()["sh"]}
    assert sh["100630"]["l"] == "Riz semi-blanchi" and sh["87032310"]["dd"] == 20.5 and sh["87032310"]["ac"] == 5
    assert "1006" in sh  # fusion : les codes existants restent
    bad = c.post("/params/sh/import", json={"csv": "1006;Riz;dix\nX;Rien;5"})
    assert bad.status_code == 422 and len(bad.json()["detail"]["erreurs"]) == 2
    r = c.post("/params/sh/import", json={"csv": "8471,Ordinateurs,5,0", "mode": "remplacer"}).json()
    assert r["total"] == 1 and [x["c"] for x in c.get("/params").json()["sh"]] == ["8471"]
    c.put("/params", json=p0)


def test_societe_dans_relances(c):
    assert c.get("/societe").json()["nom"] == "Alliance Transit"
    r = c.put("/societe", json={"nom": "Alliance Transit SARL", "ville": "Conakry", "nif": "NIF-ALL-001", "signature": "Le service recouvrement"})
    assert r.status_code == 200 and c.get("/societe").json()["nif"] == "NIF-ALL-001"
    from app.routes.finance import _lettre
    from app.routes.admin import get_societe
    from app.db import SessionLocal
    from types import SimpleNamespace as N
    f = N(relances=0, num="FA-X", date_emission=date.today(), echeance=date.today(), jours_retard=3, dossier_num="D-1", solde=10, devise="GNF")
    with SessionLocal() as db:
        lettre = _lettre(f, get_societe(db))
        assert "Le service recouvrement – Alliance Transit SARL" in lettre
        assert "Madame, Monsieur," in lettre and "(3 jours de retard), dossier D-1" in lettre  # la ponctuation survit
    assert c.put("/societe", json={"nom": "X"}).status_code == 422


def test_systeme_et_export(c):
    s = c.get("/admin/systeme").json()
    assert s["base_de_donnees"] == "sqlite" and "clients" in s["volumes"] and s["integrations"][0]["etat"] == "simulé"
    e = c.get("/admin/export.json")
    assert e.status_code == 200 and "attachment" in e.headers["content-disposition"]
    data = e.json()["tables"]
    assert "users" in data and all("pwd" not in u for u in data["users"])
    assert all("contenu" not in d for d in data["documents"])


def test_droits(c):
    c.post("/users", json={"email": "dir.adm@a.gn", "nom": "Direction", "role": "Direction", "password": "MotDePasse!123"})
    t = c.post("/auth/login", data={"username": "dir.adm@a.gn", "password": "MotDePasse!123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    assert c.get("/audit", headers=h).status_code == 200  # la direction consulte le journal
    assert c.put("/societe", json={"nom": "Pirate"}, headers=h).status_code == 403
    assert c.get("/admin/export.json", headers=h).status_code == 403
    assert c.get("/societe", headers=h).status_code == 200  # utile pour imprimer
