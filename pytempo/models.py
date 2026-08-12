"""Structuri de date pure (fără comportament de rețea)."""
from dataclasses import dataclass, field


@dataclass
class Node:
    """Un nod din arborele de domenii (nu e indicator, nu are dimensiuni)."""
    code: str
    name: str = ""


@dataclass
class Option:
    """O opțiune a unei dimensiuni (ex. 'Cluj', 'Anul 2020')."""
    label: str
    nom_item_id: int          # codul trimis în query (encQuery)
    offset: int | None = None
    parent_id: int | None = None
    depth: int | None = None  # adâncimea în arborele parentId = nivel (adevăr de structură)


@dataclass
class Dimension:
    """O dimensiune a unei matrice (ex. 'Judete', 'Perioade', 'Sexe')."""
    label: str
    dim_code: int
    dim_index: int            # poziția în dimensionsMap; CONTEAZĂ pentru ordinea din encQuery
    options: list[Option] = field(default_factory=list)
    role: str = "alt"         # 'teritoriu' | 'timp' | 'caen' | 'um' | 'alt'
