def milliers(v, decimales: int = 0) -> str:
    """Montant avec espaces comme séparateur de milliers : 1234567.5 -> « 1 234 568 »."""
    return f"{v:,.{decimales}f}".replace(",", " ")
