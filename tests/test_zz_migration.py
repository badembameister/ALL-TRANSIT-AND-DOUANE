"""Migration automatique des colonnes : ajout, idempotence, échec bloquant, démarrage concurrent.
Chaque test travaille sur sa propre base SQLite, sans toucher à celle des autres tests."""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")

import pytest  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

import app.db as db  # noqa: E402
import app.models  # noqa: E402,F401  (déclare toutes les tables)


@pytest.fixture
def base_ancienne(monkeypatch):
    """Base au schéma complet, puis amputée de deux colonnes comme une base de production plus ancienne."""
    e = create_engine(f"sqlite:///{tempfile.mkdtemp()}/old.db")
    db.Base.metadata.create_all(e)
    with e.begin() as cx:
        cx.execute(text("ALTER TABLE clients DROP COLUMN notes"))
        cx.execute(text("ALTER TABLE declarations DROP COLUMN quittance_ref"))
    monkeypatch.setattr(db, "engine", e)
    return e


def colonnes(e, table):
    return {c["name"] for c in inspect(e).get_columns(table)}


def test_ajout_et_idempotence(base_ancienne, capsys):
    ajouts = db.sync_columns()
    assert sorted(ajouts) == ["clients.notes", "declarations.quittance_ref"]
    assert "notes" in colonnes(base_ancienne, "clients")
    assert "[migration] colonnes ajoutées" in capsys.readouterr().out
    with base_ancienne.begin() as cx:  # la valeur par défaut s'applique aux lignes existantes et nouvelles
        cx.execute(text("INSERT INTO clients (code, nom, nif, devise, delai_paiement, contact) VALUES ('C1', 'X', '', 'GNF', 30, '')"))
        assert cx.execute(text("SELECT notes FROM clients")).scalar() == ""
    assert db.sync_columns() == []


def test_echec_reel_bloquant(base_ancienne, monkeypatch):
    vrai_text = db.text
    monkeypatch.setattr(db, "text", lambda sql: vrai_text(sql.replace("ALTER TABLE", "ALTER TABL")))
    with pytest.raises(db.MigrationError) as e:
        db.sync_columns()
    msg = str(e.value)
    assert "clients.notes" in msg and "declarations.quittance_ref" in msg and "syntax error" in msg


def test_colonne_mal_creee_detectee(base_ancienne, monkeypatch):
    """Même si l'ALTER « réussit » sans créer la bonne colonne, la vérification finale bloque."""
    vrai_text = db.text
    monkeypatch.setattr(db, "text", lambda sql: vrai_text(sql.replace(" notes ", " notes_bis ").replace(" quittance_ref ", " q_bis ")))
    with pytest.raises(db.MigrationError, match="clients.notes"):
        db.sync_columns()


def test_demarrage_concurrent(base_ancienne, monkeypatch):
    """Un autre démarrage ajoute la colonne entre le constat et l'ALTER : l'erreur est ignorée car la colonne existe."""
    vraie = db._colonnes_manquantes
    appels = {"n": 0}

    def perimee():
        appels["n"] += 1
        manquantes = vraie()
        if appels["n"] == 1:
            with base_ancienne.begin() as cx:  # l'autre instance passe devant
                cx.execute(text("ALTER TABLE clients ADD COLUMN notes TEXT DEFAULT ''"))
                cx.execute(text("ALTER TABLE declarations ADD COLUMN quittance_ref VARCHAR(60) DEFAULT ''"))
        return manquantes

    monkeypatch.setattr(db, "_colonnes_manquantes", perimee)
    assert db.sync_columns() == []  # les deux ALTER ont échoué (doublon), sans erreur au final
    assert appels["n"] == 2
