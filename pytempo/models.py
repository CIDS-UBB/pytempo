"""Plain data structures, with no network behaviour."""
from dataclasses import dataclass, field


@dataclass
class Node:
    """A node in the domain tree (not an indicator, so it has no dimensions)."""
    code: str
    name: str = ""


@dataclass
class Option:
    """One option of a dimension, for example 'Cluj' or 'Anul 2020'."""
    label: str
    nom_item_id: int          # the code sent in the query (encQuery)
    offset: int | None = None
    parent_id: int | None = None
    depth: int | None = None  # depth in the parentId tree


@dataclass
class Dimension:
    """One dimension of a matrix, for example 'Judete', 'Perioade', 'Sexe'."""
    label: str
    dim_code: int
    dim_index: int            # position in dimensionsMap; it drives encQuery order
    options: list[Option] = field(default_factory=list)
    role: str = "alt"         # 'teritoriu' | 'timp' | 'caen' | 'um' | 'alt'
    # for a territorial dimension, the finest real level it reaches:
    # 'localitate', 'judet', ... or 'necunoscut'. Empty for the rest. It is
    # what tells a locality dimension from a county one without reading labels
    finest_level: str = ""
