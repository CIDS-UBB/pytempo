"""Obiectul Matrix: identitate + metadate + (mai târziu) date.

Endpoint-ul e definit de cod: totul pornește din t.matrix('FOM104D').
Căutarea (catalog.search) întoarce Matrix cu code + name + url; metadatele
și datele se aduc la iterațiile 2 și 3.
"""
from dataclasses import dataclass, field

from . import client, endpoints


@dataclass
class Matrix:
    """Un indicator TEMPO. După search are code + name; restul se populează leneș."""
    code: str
    name: str = ""
    definition: str = ""
    methodology: str = ""
    observations: str = ""
    last_updated: str = ""
    periodicity: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    dimensions: list = field(default_factory=list)
    details: dict = field(default_factory=dict)

    @property
    def url(self) -> str:
        """Linkul către metadatele acestui indicator (GET matrix/{cod})."""
        return endpoints.matrix(self.code)

    def link_ok(self) -> bool:
        """True dacă linkul indicatorului răspunde. Pentru testul de linkuri."""
        return client.url_ok(self.url)

    @property
    def levels(self) -> list[str]:
        """Nivelele teritoriale prezente. Iterația 2."""
        raise NotImplementedError("iterația 2")

    def info(self) -> dict:
        """Metadatele complete. Iterația 2."""
        raise NotImplementedError("iterația 2")

    def get(self, level: str | None = None, levels: list[str] | None = None):
        """Datele indicatorului, ca DataFrame, cu filtru opțional pe nivel. Iterația 3."""
        raise NotImplementedError("iterația 3")

    def __repr__(self) -> str:
        return f"Matrix({self.code!r}, {self.name!r})"


def matrix(cod: str) -> Matrix:
    """Construiește un Matrix aducând metadatele (GET matrix/{cod}). Iterația 2."""
    raise NotImplementedError("iterația 2")


def info(cod: str) -> dict:
    """Scurtătură: metadatele unui indicator. Iterația 2."""
    raise NotImplementedError("iterația 2")


def get(cod: str, level: str | None = None, levels: list[str] | None = None):
    """Scurtătură: datele unui indicator. Iterația 3."""
    raise NotImplementedError("iterația 3")
