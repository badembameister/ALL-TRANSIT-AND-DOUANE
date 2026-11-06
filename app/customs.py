"""Règles métier douanières : documents obligatoires, contrôles, liquidation des droits et taxes.
Les taux viennent des paramètres (table `params`), jamais du code."""
from decimal import ROUND_HALF_UP, Decimal as D

DOC_TYPES = {
    "facture": "Facture commerciale", "packing": "Packing list", "bl": "Connaissement / LTA",
    "cmr": "Lettre de voiture CMR", "origine": "Certificat d'origine", "dum": "DUM / déclaration",
    "quittance": "Quittance de paiement", "autre": "Autre document",
}
DEFAULT_PARAMS = {
    "base": "GNF",
    "rates": {"GNF": 1, "EUR": 10000, "USD": 8600},  # indicatifs : à mettre à jour
    "tva": 18, "dd0": 10,
    "reg": ["Mise à la consommation", "Transit", "Entrepôt", "Admission temporaire", "Réexportation"],
    "taxes": [  # à valider avec une quittance SYDONIA World réelle
        {"n": "Redevance statistique (à valider)", "t": 1, "base": "cif", "exp": False},
        {"n": "Prélèvement communautaire CEDEAO (à valider)", "t": 0.5, "base": "cif", "exp": False},
    ],
    "sh": [
        {"c": "8703", "l": "Véhicules de tourisme", "dd": 20, "ac": 0},
        {"c": "1006", "l": "Riz", "dd": 10, "ac": 0},
        {"c": "8471", "l": "Machines informatiques", "dd": 5, "ac": 0},
        {"c": "2523", "l": "Ciments", "dd": 20, "ac": 0},
        {"c": "8429", "l": "Engins de terrassement", "dd": 5, "ac": 0},
    ],
}


def required_docs(type_: str) -> list[str]:
    if type_ == "Export":
        return ["facture", "packing"]
    if type_.startswith("Transit") or type_ == "T1/T2":
        return ["facture", "packing", "cmr"]
    return ["facture", "packing", "bl"]


def controls(d, doc_types: set[str]) -> list[dict]:
    c = [
        ("Poids brut renseigné", d.poids > 0), ("Valeur déclarée renseignée", d.valeur > 0),
        ("Nombre de colis renseigné", d.colis > 0),
        ("Code SH valide (6 à 10 chiffres)", d.code_sh.isdigit() and 6 <= len(d.code_sh) <= 10),
    ]
    c += [(f"Document obligatoire : {DOC_TYPES[k]}", k in doc_types) for k in required_docs(d.type)]
    return [{"controle": n, "conforme": bool(ok)} for n, ok in c]


def _r(x: D) -> D:
    return x.quantize(D("1"), ROUND_HALF_UP)


def compute(d, params: dict) -> dict:
    """Liquidation en devise de base. TVA sur CIF + droits + taxes + accise. Export : exonéré."""
    export = d.type == "Export"
    rate = D(str(params["rates"].get(d.devise, 1)))
    cif = d.valeur * rate + d.fret + d.assurance
    sh = next((s for s in params["sh"] if d.code_sh.startswith(s["c"])), None)
    taux_dd = D(0) if export else D(str(sh["dd"] if sh else params["dd0"]))
    droit = cif * taux_dd / 100
    lignes = []
    for t in params["taxes"]:
        if export and not t.get("exp"):
            continue
        base = cif + droit if t["base"] == "cifdd" else cif
        lignes.append({"nom": t["n"], "taux": t["t"], "montant": _r(base * D(str(t["t"])) / 100)})
    taux_ac = D(0) if (export or not sh) else D(str(sh.get("ac", 0)))
    accise = (cif + droit) * taux_ac / 100
    autres = sum((x["montant"] for x in lignes), D(0))
    tva = D(0) if export else (cif + droit + autres + accise) * D(str(params["tva"])) / 100
    total = _r(droit) + autres + _r(accise) + _r(tva)
    return {
        "devise_base": params["base"], "valeur_cif": _r(cif), "code_sh_connu": bool(sh),
        "droit_douane": {"taux": taux_dd, "montant": _r(droit)}, "autres_taxes": lignes,
        "accise": {"taux": taux_ac, "montant": _r(accise)},
        "tva": {"taux": D(0) if export else D(str(params["tva"])), "montant": _r(tva)}, "total": total,
    }
