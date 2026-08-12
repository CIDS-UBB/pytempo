"""Transformă CSV-ul de la pivot în rânduri tidy / DataFrame.

CSV-ul întoarce denumiri (label), nu coduri. Codurile INS se recuperează prin join
label -> opțiuni. Nivelul se atașează din territory (adâncimea opțiunii teritoriale).
"""


def pivot_csv_to_rows(csv_text: str, matrix) -> list[dict]:
    """Parsează CSV-ul într-o listă de dicționare, o observație per rând."""
    raise NotImplementedError("iterația 3")


def to_dataframe(rows: list[dict]):
    """Rânduri -> pandas.DataFrame (format lung)."""
    raise NotImplementedError("iterația 3")
