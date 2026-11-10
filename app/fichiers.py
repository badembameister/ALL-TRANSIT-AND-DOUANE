"""Garde-fous sur les fichiers reçus et sur les exports CSV."""
import re
import unicodedata
from pathlib import PurePosixPath

from fastapi import HTTPException

# Premiers octets attendus selon l'extension : un fichier renommé (.exe en .pdf, page HTML en .png…) est refusé.
_SIGNATURES = {".pdf": (b"%PDF",), ".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
               ".xlsx": (b"PK\x03\x04",), ".docx": (b"PK\x03\x04",)}


def nom_sur(nom: str | None) -> str:
    """Nom de fichier sans chemin, sans caractère de contrôle ni caractère pouvant casser une page ou un en-tête."""
    nom = unicodedata.normalize("NFC", (nom or "").replace("\\", "/"))
    nom = PurePosixPath(nom).name
    nom = "".join(ch for ch in nom if unicodedata.category(ch)[0] != "C")
    nom = re.sub(r"[<>:\"'`|?*;&%$]", "_", nom).strip(" .")
    if len(nom) > 120:
        base, _, ext = nom.rpartition(".")
        nom = (base[:110] + "." + ext[:9]) if base else nom[:120]
    return nom or "document"


def verifier_contenu(ext: str, contenu: bytes) -> None:
    if not contenu:
        raise HTTPException(422, "Fichier vide")
    if not contenu.startswith(_SIGNATURES.get(ext, ())):
        raise HTTPException(415, "Le contenu du fichier ne correspond pas à son extension")


def cellule_csv(v):
    """Neutralise les formules (=, +, -, @) qu'un tableur exécuterait à l'ouverture d'un export."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v
