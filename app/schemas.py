import datetime as _dt
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .security import ROLES

Type_ = Literal["Import", "Export", "Transit national", "Transit international", "T1/T2", "Entrepôt", "Réexport"]
Statut = Literal["Ouvert", "En cours", "Bloqué", "Livré", "Clôturé"]
Role = Literal[tuple(ROLES)]  # type: ignore[valid-type]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def strong(p: str) -> str:
    if len(p) < 10 or not any(c.isalpha() for c in p) or not any(c.isdigit() for c in p):
        raise ValueError("Le mot de passe doit contenir au moins 10 caractères, avec des lettres et des chiffres")
    return p


def clean_email(e: str) -> str:
    e = e.strip().lower()
    if "@" not in e or " " in e or len(e) < 5:
        raise ValueError("Adresse e-mail invalide")
    return e


class UserIn(BaseModel):
    email: str
    nom: str = Field(min_length=2)
    role: Role
    password: str
    client_id: Optional[int] = None
    _e = field_validator("email")(clean_email)
    _p = field_validator("password")(strong)


class UserPatch(BaseModel):
    nom: Optional[str] = Field(default=None, min_length=2)
    role: Optional[Role] = None
    actif: Optional[bool] = None
    client_id: Optional[int] = None


class PasswordIn(BaseModel):
    password: str
    _p = field_validator("password")(strong)


class ChangePwdIn(BaseModel):
    ancien: str
    nouveau: str
    _p = field_validator("nouveau")(strong)


class UserOut(ORM):
    id: int
    email: str
    nom: str
    role: str
    client_id: Optional[int]
    actif: bool


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
    agent_douanier: str = ""
    incoterm: Literal["", "EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"] = ""
    lieu_livraison: str = ""


class DossierOut(DossierIn, ORM):
    id: int
    num: str
    statut: str
    completude: int
    created_at: datetime
    client_nom: str = ""
    transit_statut: str = ""
    declaration_statut: str = ""
    facture_statut: str = ""
    incoterm: str = ""

    @field_validator("agent_douanier", "incoterm", "lieu_livraison", "regime", "ref", "fournisseur", "destinataire",
                     "transporteur", "origine", mode="before")
    @classmethod
    def _texte(cls, v):
        return v or ""


class JalonIn(BaseModel):
    prevue: Optional[date] = None
    reelle: Optional[date] = None


CategorieCout = Literal["Transport", "Manutention", "Magasinage", "Frais portuaires", "Droits et taxes", "Honoraires agent",
                        "Frais bancaires", "Autre"]


class CoutIn(BaseModel):
    categorie: CategorieCout
    libelle: str = Field(min_length=2)
    fournisseur: str = ""
    montant: Decimal = Field(gt=0)
    devise: str = "GNF"
    date: Optional[_dt.date] = None


class CoutOut(ORM):
    id: int
    categorie: str
    libelle: str
    fournisseur: str
    montant: float
    devise: str
    date: date
    saisi_par: str


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


class PassageIn(BaseModel):
    bureau: str = Field(min_length=2)


class TransitIn(BaseModel):
    bureau_depart: str = Field(min_length=2)
    bureau_destination: str = Field(min_length=2)
    bureaux_passage: list[str] = Field(default_factory=list, description="Bureaux de passage, dans l'ordre")
    itineraire: str = ""
    expediteur: str = ""
    destinataire: str = ""
    transporteur: str = ""
    marchandises: str = ""
    vehicule: str = ""
    vehicule_id: Optional[int] = None
    chauffeur_id: Optional[int] = None
    scelle: str = Field(default="", max_length=60, description="Numéros de scellés, séparés par des virgules")
    garantie: str = ""
    garantie_montant: Decimal = Field(default=0, ge=0)
    delai_jours: int = Field(default=7, ge=1, le=90)


class TransitOut(ORM):
    id: int
    dossier_id: int
    num: str = ""
    ref_douane: str = ""
    statut: str
    bureau_depart: str
    bureau_destination: str
    passages: list = []
    itineraire: str = ""
    expediteur: str = ""
    destinataire: str = ""
    transporteur: str = ""
    marchandises: str = ""
    vehicule: str
    vehicule_id: Optional[int] = None
    chauffeur_id: Optional[int] = None
    chauffeur_nom: str = ""
    scelle: str
    garantie: str
    garantie_montant: Decimal = Decimal(0)
    delai_jours: int
    depart: Optional[date]
    echeance: Optional[date]
    arrivee: Optional[date] = None
    apurement: Optional[date] = None
    incidents: list = []
    messages: list = []
    en_retard: bool
    scelle_casse: bool
    dossier_num: str
    client_nom: str

    @field_validator("passages", "messages", "incidents", mode="before")
    @classmethod
    def _liste(cls, v):
        return v or []

    @field_validator("num", "ref_douane", "itineraire", "expediteur", "destinataire", "transporteur", "marchandises",
                     mode="before")
    @classmethod
    def _texte(cls, v):
        return v or ""


class TransitionIn(BaseModel):
    to: Literal["En préparation", "Déposée", "Acceptée", "En circulation", "Contrôlée", "Arrivée à destination",
                "Apurée", "Rejetée"]
    motif: str = ""
    ref_douane: str = ""


class IncidentIn(BaseModel):
    type: Literal["Retard", "Contrôle", "Scellé cassé", "Anomalie", "Régularisation"]
    note: str = ""


class TransitMessageIn(BaseModel):
    sens: Literal["envoi", "réception", "interne"]
    texte: str = Field(min_length=2)


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
    dossier_num: str = ""
    client_nom: str = ""
    type_operation: str = ""
    regime: str = ""
    created_at: Optional[datetime] = None
    transmise_le: Optional[datetime] = None
    reponse_le: Optional[datetime] = None
    bae_le: Optional[datetime] = None
    ref_douane: str = ""
    montant_liquide: Optional[float] = None
    quittance_ref: str = ""
    quittance_montant: Optional[float] = None
    quittance_date: Optional[date] = None
    delai_jours: Optional[float] = None
    attente_jours: Optional[int] = None

    @field_validator("ref_douane", "quittance_ref", mode="before")
    @classmethod
    def _txt(cls, v):
        return v or ""


class QuittanceIn(BaseModel):
    ref: str = Field(min_length=3, description="Numéro de quittance délivré par le Trésor / la douane")
    montant: Decimal = Field(gt=0, description="Montant payé, en devise de base")
    date: Optional[_dt.date] = None


class MessageIn(BaseModel):
    statut: Literal["Acceptée", "Contrôle", "Rejetée", "Bon à enlever"]
    texte: str = ""
    ref_douane: str = ""


class LigneIn(BaseModel):
    libelle: str = Field(min_length=2)
    montant: Decimal = Field(gt=0, description="Montant en devise de base")


class FactureIn(BaseModel):
    lignes: list[LigneIn] = []
    refacturer_debours: bool = False


class LigneOut(ORM):
    libelle: str
    montant: float


ModeReglement = Literal["Virement", "Chèque", "Espèces", "Mobile money", "Carte", "Compensation", "Avance"]


class PaiementIn(BaseModel):
    montant: Decimal = Field(gt=0, description="Montant en devise de la facture")
    mode: ModeReglement = "Virement"
    reference: str = ""
    date: Optional[_dt.date] = None


class PaiementOut(ORM):
    id: int
    date: date
    montant: float
    mode: str = "Virement"
    reference: str = ""

    @field_validator("mode", "reference", mode="before")
    @classmethod
    def _txt(cls, v):
        return v or ""


class AvoirIn(BaseModel):
    montant: Decimal = Field(gt=0, description="Montant en devise de la facture")
    motif: str = Field(min_length=3)


class AvoirOut(ORM):
    id: int
    num: str
    date: date
    motif: str
    montant: float


class AvanceIn(BaseModel):
    montant: Decimal = Field(gt=0, description="Montant en devise du client")
    mode: ModeReglement = "Virement"
    reference: str = ""
    date: Optional[_dt.date] = None


class AvanceOut(ORM):
    id: int
    dossier_id: int
    date: date
    montant: float
    devise: str
    mode: str
    reference: str
    facture_id: Optional[int]


class FactureOut(ORM):
    id: int
    num: str
    dossier_id: int
    dossier_num: str
    client_id: int
    client_nom: str
    devise: str
    date_emission: date
    echeance: date
    lignes: list[LigneOut]
    paiements: list[PaiementOut]
    avoirs: list[AvoirOut] = []
    total: float
    paye: float
    total_avoirs: float
    solde: float
    statut: str
    relances: int
    derniere_relance: Optional[date] = None
    jours_retard: int
    devis_id: Optional[int] = None


class DevisIn(BaseModel):
    lignes: list[LigneIn] = Field(min_length=1)
    validite_jours: int = Field(default=30, ge=1, le=180)
    conditions: str = ""


class DevisOut(ORM):
    id: int
    num: str
    dossier_id: int
    dossier_num: str
    client_id: int
    client_nom: str
    devise: str
    date_emission: date
    validite: date
    statut: str
    conditions: str
    lignes: list
    total: float
    expire: bool
    cree_par: str


class DevisStatutIn(BaseModel):
    statut: Literal["Envoyé", "Accepté", "Refusé"]


class FacturerDevisIn(BaseModel):
    refacturer_debours: bool = False


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


# --- Transport et suivi opérationnel ---
TypeVehicule = Literal["Camion", "Tracteur", "Remorque", "Semi-remorque", "Fourgon"]
TypeConteneur = Literal["20", "40", "40HC", "45HC", "20RF", "40RF", "Autre"]
TypeMission = Literal["Enlèvement", "Livraison", "Transfert", "Retour vide"]
StatutMission = Literal["Planifiée", "En cours", "Livrée", "Annulée"]


def iso6346(n: str) -> str:
    """Numéro de conteneur : 4 lettres (propriétaire + catégorie) + 6 chiffres + chiffre de contrôle ISO 6346."""
    n = "".join(n.split()).replace("-", "").upper()
    if len(n) != 11 or not n[:4].isalpha() or not n[4:].isdigit():
        raise ValueError("Numéro de conteneur invalide : 4 lettres puis 7 chiffres (ex. CSQU3054383)")
    val = {}
    v = 10
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if v % 11 == 0:
            v += 1
        val[ch] = v
        v += 1
    total = sum((val[c] if c.isalpha() else int(c)) * 2 ** i for i, c in enumerate(n[:10]))
    if total % 11 % 10 != int(n[10]):
        raise ValueError(f"Chiffre de contrôle incorrect pour {n} (attendu : {total % 11 % 10})")
    return n


class ChauffeurIn(BaseModel):
    nom: str = Field(min_length=2)
    telephone: str = ""
    permis: str = ""
    permis_expire: Optional[date] = None
    transporteur: str = ""
    actif: bool = True


class ChauffeurOut(ChauffeurIn, ORM):
    id: int


class VehiculeIn(BaseModel):
    immatriculation: str = Field(min_length=3)
    type: TypeVehicule = "Camion"
    marque: str = ""
    capacite_t: Decimal = Field(default=0, ge=0)
    transporteur: str = ""
    assurance_expire: Optional[date] = None
    visite_expire: Optional[date] = None
    actif: bool = True

    @field_validator("immatriculation")
    @classmethod
    def _immat(cls, v: str) -> str:
        return " ".join(v.upper().split())


class VehiculeOut(VehiculeIn, ORM):
    id: int


class ConteneurIn(BaseModel):
    numero: str
    type: TypeConteneur = "40HC"
    dossier_id: Optional[int] = None
    compagnie: str = ""
    navire: str = ""
    bl: str = ""
    plomb: str = ""
    eta: Optional[date] = None
    arrivee: Optional[date] = None
    sortie: Optional[date] = None
    retour: Optional[date] = None
    franchise_port: int = Field(default=10, ge=0)
    franchise_retour: int = Field(default=14, ge=0)
    _n = field_validator("numero")(iso6346)


class ConteneurOut(ConteneurIn, ORM):
    id: int
    statut: str
    jours_magasinage: int
    jours_detention: int
    dossier_num: str


class MissionIn(BaseModel):
    type: TypeMission
    dossier_id: Optional[int] = None
    conteneur_id: Optional[int] = None
    vehicule_id: Optional[int] = None
    chauffeur_id: Optional[int] = None
    origine: str = Field(min_length=2)
    destination: str = Field(min_length=2)
    date_prevue: date
    instructions: str = ""


class MissionOut(MissionIn, ORM):
    id: int
    num: str
    statut: str
    debut: Optional[datetime]
    fin: Optional[datetime]
    receptionnaire: str
    note_livraison: str
    signee: bool
    position: Optional[dict]
    incidents: list
    en_retard: bool
    dossier_num: str
    conteneur_num: str
    vehicule_immat: str
    chauffeur_nom: str


class MissionStatutIn(BaseModel):
    to: Literal["En cours", "Annulée"]
    motif: str = ""


class LivraisonIn(BaseModel):
    receptionnaire: str = Field(min_length=2)
    note: str = ""
    signature: str = ""  # data:image/png;base64,...

    @field_validator("signature")
    @classmethod
    def _sig(cls, v: str) -> str:
        if v and (not v.startswith("data:image/png;base64,") or len(v) > 300_000):
            raise ValueError("Signature invalide (image PNG de 300 Ko maximum)")
        return v


class PositionIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class MissionIncidentIn(BaseModel):
    type: Literal["Retard", "Panne", "Accident", "Contrôle routier", "Marchandise endommagée", "Refus de livraison", "Autre"]
    note: str = ""
