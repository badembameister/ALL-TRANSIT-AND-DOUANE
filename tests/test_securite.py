"""Sécurité : essais de connexion limités, fermeture des sessions, fichiers reçus, cloisonnement du rôle Client,
en-têtes HTTP, exports CSV et refus des valeurs par défaut en production."""
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import date
from pathlib import Path

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.fichiers import cellule_csv, nom_sur  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Tentative  # noqa: E402
from app.schemas import LivraisonIn  # noqa: E402
from app.security import MAX_PAR_COMPTE  # noqa: E402

MDP = "MotDePasse!123"
RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as cl:
        tok = cl.post("/auth/login", data={"username": "admin@alliance.local", "password": "ChangeMe!2026"}).json()
        cl.headers["Authorization"] = f"Bearer {tok['access_token']}"
        yield cl
        with SessionLocal() as db:  # ne pas laisser d'échecs comptés pour les autres fichiers de tests
            db.execute(delete(Tentative))
            db.commit()


def compte(c, role="Agent opérationnel", **extra):
    mail = f"{uuid.uuid4().hex[:8]}@secu.gn"
    u = c.post("/users", json={"email": mail, "nom": "Test Sécurité", "role": role, "password": MDP, **extra})
    assert u.status_code == 201
    return mail, u.json()["id"]


def jeton(c, mail, mdp=MDP):
    r = c.post("/auth/login", data={"username": mail, "password": mdp})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_essais_de_connexion_limites(c):
    mail, uid = compte(c)
    for _ in range(MAX_PAR_COMPTE):
        assert c.post("/auth/login", data={"username": mail, "password": "faux"}).status_code == 401
    bloque = c.post("/auth/login", data={"username": mail.upper(), "password": MDP})  # même le bon mot de passe attend
    assert bloque.status_code == 429 and "Retry-After" in bloque.headers
    # Un autre compte n'est pas touché ; l'administrateur lève le blocage en réinitialisant le mot de passe
    autre, _ = compte(c)
    assert c.post("/auth/login", data={"username": autre, "password": MDP}).status_code == 200
    assert c.post(f"/users/{uid}/password", json={"password": "Nouveau2026Pass"}).status_code == 204
    assert c.post("/auth/login", data={"username": mail, "password": "Nouveau2026Pass"}).status_code == 200
    # Adresse inconnue : même réponse qu'un mauvais mot de passe ; mot de passe démesuré : refus propre, pas d'erreur 500
    assert c.post("/auth/login", data={"username": "personne@secu.gn", "password": "x"}).json()["detail"] == "Identifiants incorrects"
    assert c.post("/auth/login", data={"username": autre, "password": "é" * 200}).status_code == 401


def test_sessions_fermees_apres_changement(c):
    mail, uid = compte(c)
    ancien = jeton(c, mail)
    autre_session = jeton(c, mail)
    r = c.post("/auth/change-password", json={"ancien": MDP, "nouveau": "Autre2026Pass"}, headers=ancien)
    assert r.status_code == 200
    nouveau = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert c.get("/auth/me", headers=nouveau).status_code == 200
    assert c.get("/auth/me", headers=ancien).status_code == 401
    assert c.get("/auth/me", headers=autre_session).status_code == 401
    # Réinitialisation par l'administrateur puis changement de rôle : les jetons en circulation tombent
    assert c.post(f"/users/{uid}/password", json={"password": "Encore2026Pass"}).status_code == 204
    assert c.get("/auth/me", headers=nouveau).status_code == 401
    h = jeton(c, mail, "Encore2026Pass")
    assert c.patch(f"/users/{uid}", json={"role": "Comptable"}).status_code == 200
    assert c.get("/auth/me", headers=h).status_code == 401
    # Mot de passe actuel deviné à répétition : bloqué
    h = jeton(c, mail, "Encore2026Pass")
    for _ in range(MAX_PAR_COMPTE):
        assert c.post("/auth/change-password", json={"ancien": "faux", "nouveau": "Autre2026Pass"}, headers=h).status_code == 403
    assert c.post("/auth/change-password", json={"ancien": "Encore2026Pass", "nouveau": "Autre2026Pass"}, headers=h).status_code == 429


def test_jeton_falsifie_et_saisies_refusees(c):
    assert c.get("/auth/me", headers={"Authorization": "Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIn0."}).status_code == 401
    base = {"nom": "X Y", "role": "Comptable"}
    assert c.post("/users", json={**base, "email": "long@secu.gn", "password": "Aa1" + "x" * 80}).status_code == 422
    for mail in ('"><img src=x>@a.gn', "a@b", "a b@c.gn", "sans-arobase.gn"):
        assert c.post("/users", json={**base, "email": mail, "password": MDP}).status_code == 422
    with pytest.raises(ValidationError):
        LivraisonIn(receptionnaire="M. Camara", signature='data:image/png;base64,"><script>alert(1)</script>')
    assert LivraisonIn(receptionnaire="M. Camara", signature="data:image/png;base64,iVBORw0KGgo=").signature


def test_fichiers_recus(c):
    cli = c.post("/clients", json={"nom": "Sécu Import", "nif": f"NIF-{uuid.uuid4().hex[:8]}"}).json()
    d = c.post("/dossiers", json=dict(type="Import", client_id=cli["id"], ref="PO-S", designation="Riz", code_sh="100630",
                                      colis=1, poids=1000, valeur=1000, devise="USD")).json()
    url = f"/dossiers/{d['id']}/documents"
    piege = "../../a\\');alert(document.cookie);//<b>.pdf"
    up = c.post(url, data={"type": "facture"}, files={"fichier": (piege, b"%PDF-1.4 ok")})
    assert up.status_code == 201
    nom = up.json()["nom_fichier"]
    assert nom.endswith(".pdf") and not any(ch in nom for ch in "\\'\"<>/;")
    # Contenu qui ne correspond pas à l'extension : page HTML ou exécutable renommés
    assert c.post(url, data={"type": "facture"}, files={"fichier": ("f.pdf", b"<html><script>1</script>")}).status_code == 415
    assert c.post(url, data={"type": "facture"}, files={"fichier": ("f.png", b"MZ\x90\x00")}).status_code == 415
    assert c.post(url, data={"type": "facture"}, files={"fichier": ("f.pdf", b"")}).status_code == 422
    assert c.post(f"/clients/{cli['id']}/pieces", data={"type": "Agrément"}, files={"fichier": ("a.pdf", b"MZ")}).status_code == 415
    assert nom_sur("C:\\Users\\x\\facture finale.PDF") == "facture finale.PDF"
    assert nom_sur("") == "document" and len(nom_sur("a" * 300 + ".pdf")) <= 120 and nom_sur("a" * 300 + ".pdf").endswith(".pdf")


def test_client_ne_voit_pas_les_notes_internes(c):
    cli = c.post("/clients", json={"nom": "Sécu Portail", "nif": f"NIF-{uuid.uuid4().hex[:8]}"}).json()
    d = c.post("/dossiers", json=dict(type="Import", client_id=cli["id"], ref="PO-C", designation="Riz", code_sh="100630",
                                      colis=1, poids=1000, valeur=1000, devise="USD")).json()
    did = d["id"]
    mail, _ = compte(c, "Client", client_id=cli["id"])
    h = jeton(c, mail)
    assert c.post(f"/dossiers/{did}/declaration").status_code == 201
    assert any(m["sens"] == "interne" for m in c.get(f"/dossiers/{did}/declaration").json()["messages"])
    vue = c.get(f"/dossiers/{did}/declaration", headers=h)
    assert vue.status_code == 200 and all(m["sens"] != "interne" for m in vue.json()["messages"])
    assert c.get(f"/dossiers/{did}/declaration/calcul").json()["controles"]
    calc = c.get(f"/dossiers/{did}/declaration/calcul", headers=h).json()
    assert calc["controles"] == [] and calc["liquidation"]["total"] > 0

    t = c.post(f"/dossiers/{did}/transit", json={"bureau_depart": "Conakry Port", "bureau_destination": "Kourémalé"})
    assert t.status_code == 201 and c.get(f"/dossiers/{did}/transit").json()["messages"]
    vue = c.get(f"/dossiers/{did}/transit", headers=h).json()
    assert vue["bureau_depart"] == "Conakry Port" and vue["messages"] == [] and vue["incidents"] == []

    m = c.post("/missions", json=dict(type="Livraison", dossier_id=did, origine="Port", destination="Entrepôt client",
                                      date_prevue=str(date.today()), instructions="Ne pas dire au client que le camion est en panne"))
    assert m.status_code == 201
    assert c.get(f"/dossiers/{did}/missions").json()[0]["instructions"]
    vue = c.get(f"/dossiers/{did}/missions", headers=h).json()
    assert len(vue) == 1 and vue[0]["instructions"] == "" and vue[0]["destination"] == "Entrepôt client"
    for route in (f"/dossiers/{did}/journal", f"/dossiers/{did}/couts", "/users", "/admin/export.json", "/missions"):
        assert c.get(route, headers=h).status_code == 403


def test_en_tetes_et_exports(c):
    r = c.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store" and "default-src 'none'" in r.headers["content-security-policy"]
    pre = c.options("/auth/login", headers={"Origin": "https://pirate.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in pre.headers
    assert cellule_csv("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")" and cellule_csv("@SUM(A1)").startswith("'")
    assert cellule_csv("Riz blanc") == "Riz blanc" and cellule_csv(-5) == -5
    c.post("/clients", json={"nom": "=cmd|' /C calc'!A0", "nif": f"NIF-{uuid.uuid4().hex[:8]}"})
    journal = c.get("/admin/journal.csv").text
    assert not any(cell[:1] in "=+@" for ligne in journal.splitlines()[1:] for cell in ligne.split(";") if cell)
    export = c.get("/admin/export.json").json()["tables"]
    assert "tentatives" not in export and all("pwd" not in u and "jeton_v" not in u for u in export["users"])


def _demarrer(env: dict, code: str):
    propre = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "ADMIN_PASSWORD", "VERCEL", "API_DOCS")}
    propre["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/prod.db"
    return subprocess.run([sys.executable, "-c", code], cwd=RACINE, env={**propre, **env}, capture_output=True, text=True)


def test_production_refuse_les_valeurs_par_defaut():
    r = _demarrer({"VERCEL": "1"}, "import app.security")
    assert r.returncode != 0 and "SECRET_KEY" in r.stderr
    cle = {"VERCEL": "1", "SECRET_KEY": "k" * 64}
    for mdp in ({}, {"ADMIN_PASSWORD": "ChangeMe!2026"}):
        r = _demarrer({**cle, **mdp}, "import app.main as m; m.init_db()")
        assert r.returncode != 0 and "ADMIN_PASSWORD" in r.stderr
    code = "import app.main as m; m.init_db(); print(m.app.docs_url, m.app.openapi_url)"
    r = _demarrer({**cle, "ADMIN_PASSWORD": "Un-Vrai-Secret-2026"}, code)
    assert r.returncode == 0 and r.stdout.split() == ["None", "None"]
    r = _demarrer({**cle, "ADMIN_PASSWORD": "Un-Vrai-Secret-2026", "API_DOCS": "1"}, code)
    assert r.returncode == 0 and r.stdout.split() == ["/docs", "/openapi.json"]
