"""Construirea interogării și spargerea cererilor mari. Portat din pachetul R.

Matricele la nivel de localitate nu încap într-un singur POST: FOM104D are 43 de
județe și 3183 de localități, adică milioane de celule. Se descarcă județ cu
județ, folosind parentId, care leagă localitatea de județul ei, iar dacă un
singur județ tot e prea mare, localitățile lui se sparg în grupuri.

Atenție: details.matMaxDim e numărul de dimensiuni, nu o limită de celule. Nu îl
folosi ca prag de spargere.
"""
from . import territory

# pragul peste care un singur POST la pivot nu mai e rezonabil
MAX_CELLS = 100000


def split_options(codes: list[int], size: int = 100) -> list[list[int]]:
    """Sparge o listă de coduri în grupuri de cel mult `size` (din R)."""
    return [codes[i:i + size] for i in range(0, len(codes), size)]


def build_encquery(selection_per_dim: list[list[int]]) -> str:
    """Construiește encQuery: coduri separate prin virgulă în fiecare dimensiune,
    dimensiunile separate prin ':'. ORDINEA e cea din dimensionsMap (dim_index)."""
    return ":".join(",".join(str(c) for c in dim) for dim in selection_per_dim)


def cells(selection: list[list[int]]) -> int:
    """Câte celule ar cere o selecție: produsul opțiunilor pe dimensiune."""
    total = 1
    for codes in selection:
        total *= len(codes)
    return total


def _payload(matrix, selection: list[list[int]]) -> dict:
    """Corpul unui POST la pivot, pentru o selecție dată."""
    return {
        "language": "ro",
        "encQuery": build_encquery(selection),
        "matCode": matrix.code,
        "matMaxDim": matrix.details.get("matMaxDim"),
        "matUMSpec": matrix.details.get("matUMSpec"),
    }


def _locality_index(matrix) -> int | None:
    """Poziția dimensiunii de localități, dacă matricea are una."""
    for i, d in enumerate(matrix.dimensions):
        if d.role == "teritoriu" and territory.is_locality_dimension(
                d, matrix.details):
            return i
    return None


def _county_index(matrix, selection, loc_index: int, parents) -> int | None:
    """Poziția dimensiunii de județe, adică cea care conține chiar parentId-urile.

    FOM104D are județul și localitatea ca dimensiuni separate. Când tragem
    localitățile unui județ, restrângem și dimensiunea de județ la acel județ:
    altfel am cere produsul cu toate cele 43, aproape tot gol, și am rămâne
    peste prag.
    """
    parents = set(parents)
    for i, d in enumerate(matrix.dimensions):
        if i == loc_index or d.role != "teritoriu":
            continue
        if parents & set(selection[i]):
            return i
    return None


def split_selection(selection: list[list[int]],
                    max_cells: int) -> list[list[list[int]]]:
    """Sparge o selecție în bucăți care încap fiecare sub prag.

    Taie dimensiunea cu cele mai multe opțiuni, în bucăți dimensionate după
    cât loc lasă celelalte. Dacă nici bucata de o singură opțiune nu ajunge,
    recursia coboară pe următoarea dimensiune. Așa orice matrice devine
    descărcabilă, doar în mai multe cereri.
    """
    if cells(selection) <= max_cells:
        return [selection]

    spargibile = [i for i, codes in enumerate(selection) if len(codes) > 1]
    if not spargibile:
        return [selection]          # o singura celula, nu mai avem ce taia

    i = max(spargibile, key=lambda k: len(selection[k]))
    restul = max(1, cells(selection) // len(selection[i]))
    marime = max(1, max_cells // restul)

    bucati = []
    for bucata in split_options(selection[i], marime):
        sub = list(selection)
        sub[i] = bucata
        bucati.extend(split_selection(sub, max_cells))
    return bucati


def plan_requests(matrix, selection: list[list[int]],
                  max_cells: int | None = None) -> list[dict]:
    """Din selecția pe dimensiuni, produce lista de payload-uri POST.

    Sub prag, un singur payload. Peste prag, câte unul per județ la matricele
    cu localități, altfel spargere pe dimensiunea cea mai mare.
    """
    if max_cells is None:
        max_cells = MAX_CELLS
    if cells(selection) <= max_cells:
        return [_payload(matrix, selection)]

    loc_index = _locality_index(matrix)
    if loc_index is None:
        return [_payload(matrix, sel)
                for sel in split_selection(selection, max_cells)]

    loc_dim = matrix.dimensions[loc_index]
    ceruta = set(selection[loc_index])
    grupuri = territory.group_localities_by_county(loc_dim)
    county_index = _county_index(matrix, selection, loc_index, grupuri)

    payloads = []
    for parent, optiuni in grupuri.items():
        ids = [o.nom_item_id for o in optiuni if o.nom_item_id in ceruta]
        if not ids:
            continue

        baza = list(selection)
        if county_index is not None and parent in selection[county_index]:
            baza[county_index] = [parent]

        sel = list(baza)
        sel[loc_index] = ids
        # un judet care tot nu incape se sparge mai departe, pe orice
        # dimensiune, nu doar pe localitati
        for bucata in split_selection(sel, max_cells):
            payloads.append(_payload(matrix, bucata))
    return payloads
