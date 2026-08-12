"""Construirea interogării și spargerea dimensiunilor mari. Portat din pachetul R.

Când o dimensiune are prea multe opțiuni (localitățile unui județ mare), se sparge
în grupuri de 100 de nomItemId, se trimit POST-uri multiple la pivot și se
concatenează CSV-urile. details.matMaxDim parametrizează limita.
"""


def split_options(codes: list[int], size: int = 100) -> list[list[int]]:
    """Sparge o listă de coduri în grupuri de cel mult `size` (din R)."""
    return [codes[i:i + size] for i in range(0, len(codes), size)]


def build_encquery(selection_per_dim: list[list[int]]) -> str:
    """Construiește encQuery: coduri separate prin virgulă în fiecare dimensiune,
    dimensiunile separate prin ':'. ORDINEA e cea din dimensionsMap (dim_index)."""
    raise NotImplementedError("iterația 3")


def plan_requests(matrix, selection) -> list[dict]:
    """Din selecția pe dimensiuni, produce lista de payload-uri POST, spărgând
    unde e nevoie ca să rămână sub matMaxDim."""
    raise NotImplementedError("iterația 3")
