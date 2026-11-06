"""Passerelle vers le système douanier (SYDONIA World en Guinée).
Le mode d'échange (API, XML, fichiers) reste à confirmer avec la douane : on code contre cette interface."""
from typing import Protocol


class CustomsGateway(Protocol):
    def submit(self, ref: str, payload: dict) -> str:
        """Transmet la déclaration et renvoie la référence d'enregistrement douanier."""


class SimulatedGateway:
    def submit(self, ref: str, payload: dict) -> str:
        return f"SIM-{ref}"


gateway: CustomsGateway = SimulatedGateway()
