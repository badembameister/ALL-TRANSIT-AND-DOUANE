"""Crée ou réinitialise un compte administrateur sur la base indiquée par DATABASE_URL.

Usage : DATABASE_URL="postgresql://..." python -m scripts.create_admin admin@exemple.com 'MotDePasse2026!'
"""
import sys

from sqlalchemy import func, select

from app.db import Base, SessionLocal, engine
from app.models import User
from app.schemas import clean_email, strong
from app.security import hash_pwd


def main(email: str, password: str) -> None:
    email, password = clean_email(email), strong(password)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        u = db.scalar(select(User).where(func.lower(User.email) == email))
        if u:
            u.pwd, u.role, u.actif, u.client_id = hash_pwd(password), "Administrateur", True, None
            print(f"Compte existant mis à jour : {email}")
        else:
            db.add(User(email=email, nom="Administrateur", role="Administrateur", pwd=hash_pwd(password)))
            print(f"Administrateur créé : {email}")
        db.commit()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
