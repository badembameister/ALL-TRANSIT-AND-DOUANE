from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .customs import required_docs
from .db import Base

Money = Numeric(18, 2)
OPEN_TRANSIT = {"En circulation", "Contrôlée", "Arrivée à destination"}


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    nom: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(40))
    pwd: Mapped[str] = mapped_column(String(200))
    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id"))
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, default="")
    nom: Mapped[str] = mapped_column(String(200))
    nif: Mapped[str] = mapped_column(String(60))
    devise: Mapped[str] = mapped_column(String(3), default="GNF")
    delai_paiement: Mapped[int] = mapped_column(default=30)
    contact: Mapped[str] = mapped_column(String(200), default="")


class Dossier(Base):
    __tablename__ = "dossiers"
    id: Mapped[int] = mapped_column(primary_key=True)
    num: Mapped[str] = mapped_column(String(30), unique=True, default="")
    type: Mapped[str] = mapped_column(String(40))
    regime: Mapped[str] = mapped_column(String(80), default="")
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    ref: Mapped[str] = mapped_column(String(80), default="")
    fournisseur: Mapped[str] = mapped_column(String(200), default="")
    destinataire: Mapped[str] = mapped_column(String(200), default="")
    transporteur: Mapped[str] = mapped_column(String(200), default="")
    designation: Mapped[str] = mapped_column(Text)
    code_sh: Mapped[str] = mapped_column(String(12))
    colis: Mapped[int] = mapped_column(default=0)
    poids: Mapped[Decimal] = mapped_column(Money, default=0)
    valeur: Mapped[Decimal] = mapped_column(Money, default=0)
    devise: Mapped[str] = mapped_column(String(3))
    origine: Mapped[str] = mapped_column(String(80), default="")
    fret: Mapped[Decimal] = mapped_column(Money, default=0)
    assurance: Mapped[Decimal] = mapped_column(Money, default=0)
    statut: Mapped[str] = mapped_column(String(20), default="Ouvert")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    client: Mapped[Client] = relationship()
    transit: Mapped[Optional["Transit"]] = relationship(back_populates="dossier", uselist=False)
    declaration: Mapped[Optional["Declaration"]] = relationship(back_populates="dossier", uselist=False)
    facture: Mapped[Optional["Facture"]] = relationship(back_populates="dossier", uselist=False)
    documents: Mapped[list["Document"]] = relationship(back_populates="dossier", order_by="Document.id")

    @property
    def completude(self) -> int:
        req, have = required_docs(self.type), {x.type for x in self.documents}
        return round(100 * len([r for r in req if r in have]) / len(req))


class Transit(Base):
    __tablename__ = "transits"
    id: Mapped[int] = mapped_column(primary_key=True)
    dossier_id: Mapped[int] = mapped_column(ForeignKey("dossiers.id"), unique=True)
    statut: Mapped[str] = mapped_column(String(30), default="En préparation")
    bureau_depart: Mapped[str] = mapped_column(String(120))
    bureau_destination: Mapped[str] = mapped_column(String(120))
    vehicule: Mapped[str] = mapped_column(String(120), default="")
    scelle: Mapped[str] = mapped_column(String(60), default="")
    garantie: Mapped[str] = mapped_column(String(120), default="")
    depart: Mapped[Optional[date]] = mapped_column(Date)
    delai_jours: Mapped[int] = mapped_column(default=7)
    incidents: Mapped[list] = mapped_column(JSON, default=list)
    dossier: Mapped[Dossier] = relationship(back_populates="transit")

    @property
    def en_retard(self) -> bool:
        return bool(self.statut in OPEN_TRANSIT and self.depart and self.depart + timedelta(days=self.delai_jours) < date.today())


class Declaration(Base):
    __tablename__ = "declarations"
    id: Mapped[int] = mapped_column(primary_key=True)
    dossier_id: Mapped[int] = mapped_column(ForeignKey("dossiers.id"), unique=True)
    ref: Mapped[str] = mapped_column(String(40))
    statut: Mapped[str] = mapped_column(String(20), default="Brouillon")
    dossier: Mapped[Dossier] = relationship(back_populates="declaration")
    messages: Mapped[list["DeclMessage"]] = relationship(order_by="DeclMessage.id")


class DeclMessage(Base):
    __tablename__ = "declaration_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    declaration_id: Mapped[int] = mapped_column(ForeignKey("declarations.id"))
    sens: Mapped[str] = mapped_column(String(10))  # envoi | réception | interne
    texte: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    dossier_id: Mapped[int] = mapped_column(ForeignKey("dossiers.id"))
    type: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(default=1)
    nom_fichier: Mapped[str] = mapped_column(String(255))
    contenu: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    depose_par: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dossier: Mapped[Dossier] = relationship(back_populates="documents")


class Facture(Base):
    __tablename__ = "factures"
    id: Mapped[int] = mapped_column(primary_key=True)
    num: Mapped[str] = mapped_column(String(30), unique=True, default="")
    dossier_id: Mapped[int] = mapped_column(ForeignKey("dossiers.id"), unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    devise: Mapped[str] = mapped_column(String(3))
    date_emission: Mapped[date] = mapped_column(Date, default=date.today)
    echeance: Mapped[date] = mapped_column(Date)
    relances: Mapped[int] = mapped_column(default=0)
    dossier: Mapped[Dossier] = relationship(back_populates="facture")
    lignes: Mapped[list["FactureLigne"]] = relationship(cascade="all, delete-orphan")
    paiements: Mapped[list["Paiement"]] = relationship(cascade="all, delete-orphan")

    @property
    def total(self) -> Decimal:
        return sum((x.montant for x in self.lignes), Decimal(0))

    @property
    def paye(self) -> Decimal:
        return sum((x.montant for x in self.paiements), Decimal(0))

    @property
    def solde(self) -> Decimal:
        return self.total - self.paye

    @property
    def statut(self) -> str:
        if self.solde <= 0:
            return "Payée"
        if self.echeance < date.today():
            return "En retard"
        return "Partielle" if self.paye > 0 else "Impayée"


class FactureLigne(Base):
    __tablename__ = "facture_lignes"
    id: Mapped[int] = mapped_column(primary_key=True)
    facture_id: Mapped[int] = mapped_column(ForeignKey("factures.id"))
    libelle: Mapped[str] = mapped_column(String(200))
    montant: Mapped[Decimal] = mapped_column(Money)


class Paiement(Base):
    __tablename__ = "paiements"
    id: Mapped[int] = mapped_column(primary_key=True)
    facture_id: Mapped[int] = mapped_column(ForeignKey("factures.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    montant: Mapped[Decimal] = mapped_column(Money)


class Param(Base):
    __tablename__ = "params"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    utilisateur: Mapped[str] = mapped_column(String(200))
    entite: Mapped[str] = mapped_column(String(40))
    entite_id: Mapped[int] = mapped_column(default=0)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
