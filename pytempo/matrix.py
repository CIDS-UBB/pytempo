"""Obiectul Matrix: identitate + metadate + (mai târziu) date.

Endpoint-ul e definit de cod: totul pornește din t.matrix('FOM104D').
Căutarea (catalog.search) întoarce Matrix cu code + name + url; metadatele
și datele se aduc la iterațiile 2 și 3.
"""
from dataclasses import dataclass, field

from . import client, endpoints, territory
from .models import Dimension, Option


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
        """Nivelele teritoriale prezente, de la general la specific."""
        return territory.levels_present(self.dimensions)

    @property
    def has_siruta(self) -> bool:
        """True dacă denumirile de localitate poartă prefix SIRUTA."""
        return bool(self.details.get("matSiruta"))

    def info(self) -> dict:
        """Metadatele complete, ca dicționar."""
        return {
            "code": self.code,
            "name": self.name,
            "definition": self.definition,
            "methodology": self.methodology,
            "observations": self.observations,
            "last_updated": self.last_updated,
            "periodicity": self.periodicity,
            "sources": self.sources,
            "levels": self.levels,
            "has_siruta": self.has_siruta,
            "dimensions": [
                {
                    "index": d.dim_index,
                    "code": d.dim_code,
                    "label": d.label.strip(),
                    "role": d.role,
                    "n_options": len(d.options),
                }
                for d in self.dimensions
            ],
        }

    def get(self, level: str | None = None, levels: list[str] | None = None):
        """Datele indicatorului, ca DataFrame, cu filtru opțional pe nivel. Iterația 3."""
        raise NotImplementedError("iterația 3")

    def __repr__(self) -> str:
        return f"Matrix({self.code!r}, {self.name!r})"


def _build(cod: str, data: dict) -> Matrix:
    """Construiește un Matrix din JSON-ul brut al endpointului matrix/{cod}.

    Ordinea dimensiunilor din dimensionsMap se păstrează în dim_index: ea
    contează pentru ordinea din encQuery (iterația 3).
    """
    details = data.get("details") or {}
    dims = []
    for i, raw in enumerate(data.get("dimensionsMap") or []):
        options = [
            Option(
                label=opt.get("label", ""),
                nom_item_id=opt.get("nomItemId"),
                offset=opt.get("offset"),
                parent_id=opt.get("parentId"),
            )
            for opt in (raw.get("options") or [])
        ]
        dims.append(Dimension(
            label=raw.get("label", ""),
            dim_code=raw.get("dimCode"),
            dim_index=i,
            options=options,
        ))
    territory.assign_roles(dims, details)

    return Matrix(
        code=cod,
        name=data.get("matrixName", ""),
        definition=data.get("definitie", "") or "",
        methodology=data.get("metodologie", "") or "",
        observations=data.get("observatii", "") or "",
        last_updated=data.get("ultimaActualizare", "") or "",
        periodicity=data.get("periodicitati") or [],
        sources=data.get("surseDeDate") or [],
        dimensions=dims,
        details=details,
    )


def matrix(cod: str) -> Matrix:
    """Construiește un Matrix aducând metadatele (GET matrix/{cod})."""
    return _build(cod, client.get_json(endpoints.matrix(cod)))


def info(cod: str) -> dict:
    """Scurtătură: metadatele unui indicator."""
    return matrix(cod).info()


def get(cod: str, level: str | None = None, levels: list[str] | None = None):
    """Scurtătură: datele unui indicator. Iterația 3."""
    raise NotImplementedError("iterația 3")
