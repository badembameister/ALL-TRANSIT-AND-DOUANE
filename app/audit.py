from sqlalchemy.orm import Session

from .models import Audit, User


def audit(db: Session, user: User, entite: str, eid: int, action: str, detail: str = "") -> None:
    db.add(Audit(utilisateur=user.email, entite=entite, entite_id=eid, action=action, detail=detail))
