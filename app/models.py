from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text
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
    notifs_vues_le: Mapped[Optional[datetime]] = mapped_column(DateTime)  # portail client : dernière lecture des notifications
    jeton_v: Mapped[Optional[int]] = mapped_column(Integer)  # version des jetons : augmentée à chaque changement de mot de passe


class Tentative(Base):
    """Échec d'authentification, pour limiter les essais (en base : les fonctions Vercel n'ont pas de mémoire commune)."""
    __tablename__ = "tentatives"
    id: Mapped[int] = mapped_column(primary_key=True)
    cle: Mapped[str] = mapped_column(String(260), index=True)  # « e:adresse », « ip:adresse » ou « pw:id »
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, default="")
    nom: Mapped[str] = mapped_column(String(200))
    nif: Mapped[str] = mapped_column(String(60))
    devise: Mapped[str] = mapped_column(String(3), default="GNF")
    delai_paiement: Mapped[int] = mapped_column(default=30)
    contact: Mapped[str] = mapped_column(String(200), default="")
    # Colonnes ajoutées par la migration automatique (db.sync_columns)
    type: Mapped[str] = mapped_column(String(30), default="Client", server_default="Client")
    rc: Mapped[str] = mapped_column(String(60), default="", server_default="")  # registre du commerce (RCCM)
    adresse: Mapped[str] = mapped_column(String(300), default="", server_default="")
    ville: Mapped[str] = mapped_column(String(100), default="", server_default="")
    pays: Mapped[str] = mapped_column(String(80), default="Guinée", server_default="Guinée")
    telephone: Mapped[str] = mapped_column(String(40), default="", server_default="")
    email: Mapped[str] = mapped_column(String(200), default="", server_default="")
    banque: Mapped[str] = mapped_column(String(120), default="", server_default="")
    compte_bancaire: Mapped[str] = mapped_column(String(60), default="", server_default="")
    plafond_credit: Mapped[Decimal] = mapped_column(Money, default=0, server_default="0")  # en devise de base, 0 = sans plafond
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    actif: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    contacts: Mapped[list["Contact"]] = relationship(cascade="all, delete-orphan", order_by="Contact.id")
    pieces: Mapped[list["PiecePartenaire"]] = relationship(cascade="all, delete-orphan", order_by="PiecePartenaire.id")


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    nom: Mapped[str] = mapped_column(String(200))
    fonction: Mapped[str] = mapped_column(String(120), default="")
    telephone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    principal: Mapped[bool] = mapped_column(Boolean, default=False)


class PiecePartenaire(Base):
    """Document d'un partenaire : agrément, carte de commerçant, attestation, contrat…"""
    __tablename__ = "pieces_partenaires"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    type: Mapped[str] = mapped_column(String(40))
    nom_fichier: Mapped[str] = mapped_column(String(255))
    contenu: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    expiration: Mapped[Optional[date]] = mapped_column(Date)
    depose_par: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def expire(self) -> bool:
        return bool(self.expiration and self.expiration < date.today())


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
    # Colonnes ajoutées par la migration automatique (db.sync_columns)
    agent_douanier: Mapped[str] = mapped_column(String(200), default="", server_default="")
    incoterm: Mapped[str] = mapped_column(String(3), default="", server_default="")
    lieu_livraison: Mapped[str] = mapped_column(String(200), default="", server_default="")
    jalons: Mapped[Optional[dict]] = mapped_column(JSON)  # {clé: {"prevue": "AAAA-MM-JJ", "reelle": ...}} saisis à la main
    client: Mapped[Client] = relationship()
    couts: Mapped[list["Cout"]] = relationship(order_by="Cout.id", cascade="all, delete-orphan")
    transit: Mapped[Optional["Transit"]] = relationship(back_populates="dossier", uselist=False)
    declaration: Mapped[Optional["Declaration"]] = relationship(back_populates="dossier", uselist=False)
    facture: Mapped[Optional["Facture"]] = relationship(back_populates="dossier", uselist=False)
    documents: Mapped[list["Document"]] = relationship(back_populates="dossier", order_by="Document.id")

    @property
    def completude(self) -> int:
        req, have = required_docs(self.type), {x.type for x in self.documents}
        return round(100 * len([r for r in req if r in have]) / len(req))

    @property
    def client_nom(self) -> str:
        return self.client.nom

    @property
    def transit_statut(self) -> str:
        return self.transit.statut if self.transit else ""

    @property
    def declaration_statut(self) -> str:
        return self.declaration.statut if self.declaration else ""

    @property
    def facture_statut(self) -> str:
        return self.facture.statut if self.facture else ""


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
    # Colonnes ajoutées par la migration automatique (db.sync_columns) : valeurs par défaut côté base.
    num: Mapped[str] = mapped_column(String(30), default="", server_default="")
    ref_douane: Mapped[str] = mapped_column(String(60), default="", server_default="")
    expediteur: Mapped[str] = mapped_column(String(200), default="", server_default="")
    destinataire: Mapped[str] = mapped_column(String(200), default="", server_default="")
    transporteur: Mapped[str] = mapped_column(String(200), default="", server_default="")
    marchandises: Mapped[str] = mapped_column(Text, default="", server_default="")
    itineraire: Mapped[str] = mapped_column(Text, default="", server_default="")
    garantie_montant: Mapped[Decimal] = mapped_column(Money, default=0, server_default="0")
    vehicule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicules.id"))
    chauffeur_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chauffeurs.id"))
    passages: Mapped[Optional[list]] = mapped_column(JSON)  # [{"bureau": str, "date": "AAAA-MM-JJ" | None}]
    messages: Mapped[Optional[list]] = mapped_column(JSON)  # [{"ts", "sens", "texte"}]
    arrivee: Mapped[Optional[date]] = mapped_column(Date)
    apurement: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    dossier: Mapped[Dossier] = relationship(back_populates="transit")
    vehicule_parc: Mapped[Optional["Vehicule"]] = relationship()
    chauffeur: Mapped[Optional["Chauffeur"]] = relationship()

    @property
    def echeance(self) -> Optional[date]:
        return self.depart + timedelta(days=self.delai_jours) if self.depart else None

    @property
    def en_retard(self) -> bool:
        return bool(self.statut in OPEN_TRANSIT and self.echeance and self.echeance < date.today())

    @property
    def scelle_casse(self) -> bool:
        return any(i.get("type") == "Scellé cassé" for i in self.incidents or [])

    @property
    def dossier_num(self) -> str:
        return self.dossier.num

    @property
    def client_nom(self) -> str:
        return self.dossier.client.nom

    @property
    def chauffeur_nom(self) -> str:
        return self.chauffeur.nom if self.chauffeur else ""


class Declaration(Base):
    __tablename__ = "declarations"
    id: Mapped[int] = mapped_column(primary_key=True)
    dossier_id: Mapped[int] = mapped_column(ForeignKey("dossiers.id"), unique=True)
    ref: Mapped[str] = mapped_column(String(40))
    statut: Mapped[str] = mapped_column(String(20), default="Brouillon")
    # Colonnes ajoutées par la migration automatique (db.sync_columns)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    transmise_le: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reponse_le: Mapped[Optional[datetime]] = mapped_column(DateTime)
    bae_le: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ref_douane: Mapped[str] = mapped_column(String(60), default="", server_default="")  # référence d'enregistrement
    montant_liquide: Mapped[Optional[Decimal]] = mapped_column(Money)  # figé à la transmission
    quittance_ref: Mapped[str] = mapped_column(String(60), default="", server_default="")
    quittance_montant: Mapped[Optional[Decimal]] = mapped_column(Money)
    quittance_date: Mapped[Optional[date]] = mapped_column(Date)
    dossier: Mapped[Dossier] = relationship(back_populates="declaration")
    messages: Mapped[list["DeclMessage"]] = relationship(order_by="DeclMessage.id")

    @property
    def delai_jours(self) -> Optional[float]:
        """Délai de dédouanement : de la transmission au bon à enlever, en jours."""
        if self.transmise_le and self.bae_le:
            return round((self.bae_le - self.transmise_le).total_seconds() / 86400, 1)
        return None

    @property
    def attente_jours(self) -> Optional[int]:
        """Jours écoulés depuis la transmission, tant que le bon à enlever n'est pas obtenu."""
        if self.transmise_le and not self.bae_le and self.statut != "Rejetée":
            return (datetime.utcnow() - self.transmise_le).days
        return None

    @property
    def dossier_num(self) -> str:
        return self.dossier.num

    @property
    def client_nom(self) -> str:
        return self.dossier.client.nom

    @property
    def type_operation(self) -> str:
        return self.dossier.type

    @property
    def regime(self) -> str:
        return self.dossier.regime or ""


class DeclMessage(Base):
    __tablename__ = "declaration_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    declaration_id: Mapped[int] = mapped_column(ForeignKey("declarations.id"))
    sens: Mapped[str] = mapped_column(String(10))  # envoi | réception | interne
    texte: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Cout(Base):
    """Coût engagé sur un dossier (achat de prestation, débours) pour suivre la marge."""
    __tablename__ = "dossier_couts"
    id: Mapped[int] = mapped_column(primary_key=True)
    dossier_id: Mapped[int] = mapped_column(ForeignKey("dossiers.id"))
    categorie: Mapped[str] = mapped_column(String(40))
    libelle: Mapped[str] = mapped_column(String(200))
    fournisseur: Mapped[str] = mapped_column(String(200), default="")
    montant: Mapped[Decimal] = mapped_column(Money)
    devise: Mapped[str] = mapped_column(String(3), default="GNF")
    date: Mapped[date] = mapped_column(Date, default=date.today)
    saisi_par: Mapped[str] = mapped_column(String(200), default="")


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
    derniere_relance: Mapped[Optional[date]] = mapped_column(Date)
    devis_id: Mapped[Optional[int]] = mapped_column(ForeignKey("devis.id"))
    dossier: Mapped[Dossier] = relationship(back_populates="facture")
    client: Mapped[Client] = relationship()
    lignes: Mapped[list["FactureLigne"]] = relationship(cascade="all, delete-orphan", order_by="FactureLigne.id")
    paiements: Mapped[list["Paiement"]] = relationship(cascade="all, delete-orphan", order_by="Paiement.id")
    avoirs: Mapped[list["Avoir"]] = relationship(cascade="all, delete-orphan", order_by="Avoir.id")

    @property
    def total(self) -> Decimal:
        return sum((x.montant for x in self.lignes), Decimal(0))

    @property
    def paye(self) -> Decimal:
        return sum((x.montant for x in self.paiements), Decimal(0))

    @property
    def total_avoirs(self) -> Decimal:
        return sum((x.montant for x in self.avoirs), Decimal(0))

    @property
    def solde(self) -> Decimal:
        return self.total - self.paye - self.total_avoirs

    @property
    def jours_retard(self) -> int:
        return max(0, (date.today() - self.echeance).days) if self.solde > 0 else 0

    @property
    def client_nom(self) -> str:
        return self.client.nom

    @property
    def dossier_num(self) -> str:
        return self.dossier.num

    @property
    def statut(self) -> str:
        if self.solde <= 0:
            return "Payée" if not self.avoirs else "Soldée"
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
    mode: Mapped[str] = mapped_column(String(30), default="Virement", server_default="Virement")
    reference: Mapped[str] = mapped_column(String(80), default="", server_default="")


class Avoir(Base):
    """Avoir (note de crédit) : réduit le montant dû d'une facture, sans la modifier."""
    __tablename__ = "avoirs"
    id: Mapped[int] = mapped_column(primary_key=True)
    num: Mapped[str] = mapped_column(String(30), unique=True, default="")
    facture_id: Mapped[int] = mapped_column(ForeignKey("factures.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    motif: Mapped[str] = mapped_column(String(300))
    montant: Mapped[Decimal] = mapped_column(Money)


class Avance(Base):
    """Avance (acompte) reçue du client sur un dossier avant facturation ; imputée à la facture à sa création."""
    __tablename__ = "avances"
    id: Mapped[int] = mapped_column(primary_key=True)
    dossier_id: Mapped[int] = mapped_column(ForeignKey("dossiers.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    montant: Mapped[Decimal] = mapped_column(Money)
    devise: Mapped[str] = mapped_column(String(3))
    mode: Mapped[str] = mapped_column(String(30), default="Virement")
    reference: Mapped[str] = mapped_column(String(80), default="")
    facture_id: Mapped[Optional[int]] = mapped_column(ForeignKey("factures.id"))


class Devis(Base):
    __tablename__ = "devis"
    id: Mapped[int] = mapped_column(primary_key=True)
    num: Mapped[str] = mapped_column(String(30), unique=True, default="")
    dossier_id: Mapped[int] = mapped_column(ForeignKey("dossiers.id"))
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    devise: Mapped[str] = mapped_column(String(3))
    date_emission: Mapped[date] = mapped_column(Date, default=date.today)
    validite: Mapped[date] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(String(20), default="Brouillon")  # Brouillon | Envoyé | Accepté | Refusé | Facturé
    conditions: Mapped[str] = mapped_column(Text, default="")
    lignes: Mapped[list] = mapped_column(JSON, default=list)  # [{"libelle", "montant"}] en devise du devis
    cree_par: Mapped[str] = mapped_column(String(200), default="")
    dossier: Mapped[Dossier] = relationship()
    client: Mapped[Client] = relationship()

    @property
    def total(self) -> Decimal:
        return sum((Decimal(str(x["montant"])) for x in self.lignes or []), Decimal(0))

    @property
    def expire(self) -> bool:
        return self.statut in {"Brouillon", "Envoyé"} and self.validite < date.today()

    @property
    def client_nom(self) -> str:
        return self.client.nom

    @property
    def dossier_num(self) -> str:
        return self.dossier.num


# --- Transport et suivi opérationnel (cahier des charges, point 8) ---
MISSION_OUVERTE = {"Planifiée", "En cours"}


class Chauffeur(Base):
    __tablename__ = "chauffeurs"
    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(200))
    telephone: Mapped[str] = mapped_column(String(40), default="")
    permis: Mapped[str] = mapped_column(String(60), default="")
    permis_expire: Mapped[Optional[date]] = mapped_column(Date)
    transporteur: Mapped[str] = mapped_column(String(200), default="")
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class Vehicule(Base):
    __tablename__ = "vehicules"
    id: Mapped[int] = mapped_column(primary_key=True)
    immatriculation: Mapped[str] = mapped_column(String(30), unique=True)
    type: Mapped[str] = mapped_column(String(20))  # Camion | Tracteur | Remorque | Semi-remorque | Fourgon
    marque: Mapped[str] = mapped_column(String(80), default="")
    capacite_t: Mapped[Decimal] = mapped_column(Money, default=0)
    transporteur: Mapped[str] = mapped_column(String(200), default="")
    assurance_expire: Mapped[Optional[date]] = mapped_column(Date)
    visite_expire: Mapped[Optional[date]] = mapped_column(Date)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class Conteneur(Base):
    __tablename__ = "conteneurs"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(11), unique=True)
    type: Mapped[str] = mapped_column(String(10), default="40HC")
    dossier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dossiers.id"))
    compagnie: Mapped[str] = mapped_column(String(120), default="")
    navire: Mapped[str] = mapped_column(String(120), default="")
    bl: Mapped[str] = mapped_column(String(60), default="")
    plomb: Mapped[str] = mapped_column(String(60), default="")
    eta: Mapped[Optional[date]] = mapped_column(Date)
    arrivee: Mapped[Optional[date]] = mapped_column(Date)
    sortie: Mapped[Optional[date]] = mapped_column(Date)
    retour: Mapped[Optional[date]] = mapped_column(Date)
    franchise_port: Mapped[int] = mapped_column(default=10)   # jours sans magasinage au port
    franchise_retour: Mapped[int] = mapped_column(default=14)  # jours pour restituer le vide (détention)
    dossier: Mapped[Optional[Dossier]] = relationship()

    @property
    def statut(self) -> str:
        if self.retour:
            return "Restitué"
        if self.sortie:
            return "Sorti"
        return "Au port" if self.arrivee else "Attendu"

    @property
    def jours_magasinage(self) -> int:
        """Jours facturables au port, au-delà de la franchise."""
        if not self.arrivee:
            return 0
        return max(0, ((self.sortie or date.today()) - self.arrivee).days - self.franchise_port)

    @property
    def jours_detention(self) -> int:
        """Jours de retard de restitution du vide, au-delà de la franchise."""
        if not self.sortie:
            return 0
        return max(0, ((self.retour or date.today()) - self.sortie).days - self.franchise_retour)

    @property
    def dossier_num(self) -> str:
        return self.dossier.num if self.dossier else ""


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[int] = mapped_column(primary_key=True)
    num: Mapped[str] = mapped_column(String(30), unique=True, default="")
    type: Mapped[str] = mapped_column(String(20))  # Enlèvement | Livraison | Transfert | Retour vide
    dossier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dossiers.id"))
    conteneur_id: Mapped[Optional[int]] = mapped_column(ForeignKey("conteneurs.id"))
    vehicule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("vehicules.id"))
    chauffeur_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chauffeurs.id"))
    origine: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(200))
    date_prevue: Mapped[date] = mapped_column(Date)
    debut: Mapped[Optional[datetime]] = mapped_column(DateTime)
    fin: Mapped[Optional[datetime]] = mapped_column(DateTime)
    statut: Mapped[str] = mapped_column(String(20), default="Planifiée")
    instructions: Mapped[str] = mapped_column(Text, default="")
    receptionnaire: Mapped[str] = mapped_column(String(200), default="")
    note_livraison: Mapped[str] = mapped_column(Text, default="")
    signature: Mapped[str] = mapped_column(Text, default="", deferred=True)  # image PNG en data URL
    position: Mapped[Optional[dict]] = mapped_column(JSON)  # dernière position GPS {lat, lng, ts}
    incidents: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dossier: Mapped[Optional[Dossier]] = relationship()
    conteneur: Mapped[Optional[Conteneur]] = relationship()
    vehicule: Mapped[Optional[Vehicule]] = relationship()
    chauffeur: Mapped[Optional[Chauffeur]] = relationship()

    @property
    def en_retard(self) -> bool:
        return self.statut in MISSION_OUVERTE and self.date_prevue < date.today()

    @property
    def signee(self) -> bool:
        return bool(self.signature)

    @property
    def dossier_num(self) -> str:
        return self.dossier.num if self.dossier else ""

    @property
    def conteneur_num(self) -> str:
        return self.conteneur.numero if self.conteneur else ""

    @property
    def vehicule_immat(self) -> str:
        return self.vehicule.immatriculation if self.vehicule else ""

    @property
    def chauffeur_nom(self) -> str:
        return self.chauffeur.nom if self.chauffeur else ""


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
