from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .security import ROLES

Type_ = Literal["Import", "Export", "Transit national", "Transit international", "T1/T2", "Entrepôt", "Réexport"]
Statut = Literal["Ouvert", "En cours", "Bloqué", "Livré", "Clôturé"]
Role = Literal[tuple(ROLES)]  # type: ignore[valid-type]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserIn(BaseModel):
    email: str
    nom: str
    role: Role
    password: str = Field(min_length=10)
    client_id: Optional[int] = None


class UserOut(ORM):
    id: int
    email: str
    nom: str
    role: str
    client_id: Optional[int]


class ClientIn(BaseModel):
    nom: str
    nif: str
    devise: str = "GNF"
    delai_paiement: int = 30
    contact: str = ""


class ClientOut(ClientIn, ORM):
    id: int
    code: str


class DossierIn(BaseModel):
    type: Type_
    regime: str = "Mise à la consommation"
    client_id: int
    ref: str = ""
    fournisseur: str = ""
    destinataire: str = ""
    transporteur: str = ""
    designation: str
    code_sh: str
    colis: int = Field(ge=0)
    poids: Decimal = Field(ge=0)
    valeur: Decimal = Field(ge=0)
    devise: str
    origine: str = ""
    fret: Decimal = Field(default=0, ge=0)
    assurance: Decimal = Field(default=0, ge=0)


class DossierOut(DossierIn, ORM):
    id: int
    num: str
    statut: str
    completude: int
    created_at: datetime


class StatutIn(BaseModel):
    statut: Statut


class DocumentOut(ORM):
    id: int
    dossier_id: int
    type: str
    version: int
    nom_fichier: str
    depose_par: str
    created_at: datetime


class TransitIn(BaseModel):
    bureau_depart: str
    bureau_destination: str
    vehicule: str = ""
    scelle: str = ""
    garantie: str = ""
    delai_jours: int = Field(default=7, ge=1)


class TransitOut(TransitIn, ORM):
    id: int
    dossier_id: int
    statut: str
    depart: Optional[date]
    incidents: list
    en_retard: bool


class TransitionIn(BaseModel):
    to: str


class IncidentIn(BaseModel):
    type: Literal["Retard", "Contrôle", "Scellé cassé", "Anomalie", "Régularisation"]
    note: str = ""


class MessageOut(ORM):
    sens: str
    texte: str
    created_at: datetime


class DeclOut(ORM):
    id: int
    dossier_id: int
    ref: str
    statut: str
    messages: list[MessageOut]


class MessageIn(BaseModel):
    statut: Literal["Acceptée", "Contrôle", "Rejetée", "Bon à enlever"]
    texte: str = ""


class LigneIn(BaseModel):
    libelle: str
    montant: Decimal = Field(gt=0, description="Montant en devise de base")


class FactureIn(BaseModel):
    lignes: list[LigneIn] = []
    refacturer_debours: bool = False


class LigneOut(ORM):
    libelle: str
    montant: float


class PaiementIn(BaseModel):
    montant: Decimal = Field(gt=0, description="Montant en devise de la facture")


class PaiementOut(ORM):
    date: date
    montant: float


class FactureOut(ORM):
    id: int
    num: str
    dossier_id: int
    client_id: int
    devise: str
    date_emission: date
    echeance: date
    lignes: list[LigneOut]
    paiements: list[PaiementOut]
    total: float
    paye: float
    solde: float
    statut: str
    relances: int


class TaxIn(BaseModel):
    n: str
    t: float = Field(ge=0)
    base: Literal["cif", "cifdd"] = "cif"
    exp: bool = False


class ShIn(BaseModel):
    c: str
    l: str
    dd: float = Field(ge=0)
    ac: float = Field(default=0, ge=0)


class ParamsIn(BaseModel):
    base: str
    rates: dict[str, float]
    tva: float = Field(ge=0)
    dd0: float = Field(ge=0)
    reg: list[str]
    taxes: list[TaxIn]
    sh: list[ShIn]
