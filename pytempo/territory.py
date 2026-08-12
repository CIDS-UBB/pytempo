"""Ierarhia teritorială și nivelele, derivate din parentId.

Principiu de corectitudine: adâncimea în arborele parentId e sursa de adevăr a
nivelului. Numele nivelului (LEVEL_NAMES) e o mapare best-effort peste adâncime,
fiindcă denumirile variază între matrice. Nu inversa ordinea celor două.
"""

# mapare best-effort adâncime -> nume; adevărul rămâne adâncimea numerică
LEVEL_NAMES = {
    0: "national",
    1: "macroregiune",
    2: "regiune",
    3: "judet",
    4: "localitate",
}


def build_tree(options: list) -> None:
    """Completează option.depth pentru fiecare opțiune, urcând pe parent_id."""
    raise NotImplementedError("iterația 2")


def territorial_dimension(matrix):
    """Identifică dimensiunea teritorială (după label: Judete/Localitati/...)."""
    raise NotImplementedError("iterația 2")


def levels_present(matrix) -> list[str]:
    """Mulțimea nivelelor prezente în dimensiunea teritorială a matricei."""
    raise NotImplementedError("iterația 2")


def group_by_county(matrix) -> dict:
    """Grupează opțiunile teritoriale pe județ (prin parent_id). Baza chunking-ului
    județ cu județ pentru matricele la nivel de localitate."""
    raise NotImplementedError("iterația 3")
