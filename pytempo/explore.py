"""Discovery: walking the context tree, and the interactive explorer.

The real engine is browse() plus catalog.search(); init() is only the UI on top
of them. The interactive UI (a terminal or notebook menu) is future work; the
functions underneath are the ones that matter.
"""
from . import endpoints, client, catalog


def browse(code: str = "") -> list:
    """Walk the TEMPO context tree.

    code='' returns the top level domains (A. Statistica sociala, B. Statistica
    economica, C. Finante, D. Justitie and so on). A node code returns its
    children, so you can descend step by step to the indicators.
    """
    raise NotImplementedError("not implemented yet")


def init() -> None:
    """An interactive explorer, for poking around the data.

    It would start from the top domains, let you descend, search, filter by
    level, pick an indicator and see its info and levels. Runs in a terminal or
    a notebook. The UI is future work; it rests on browse() and search().
    """
    raise NotImplementedError("not implemented yet")
