"""Building the query and splitting large requests. Ported from the R package.

Locality level matrices do not fit in a single POST: FOM104D has 43 counties
and 3183 localities, which is millions of cells. They are downloaded county by
county, using parentId, which ties a locality to its county, and if a single
county is still too large its selection is split further.

Note: details.matMaxDim is the number of dimensions, not a cell limit. Do not
use it as a splitting threshold.
"""
from . import territory

# the point past which a single POST to pivot is no longer reasonable
MAX_CELLS = 100000


def split_options(codes: list[int], size: int = 100) -> list[list[int]]:
    """Split a list of codes into groups of at most `size` (from R)."""
    return [codes[i:i + size] for i in range(0, len(codes), size)]


def build_encquery(selection_per_dim: list[list[int]]) -> str:
    """Build encQuery: codes joined by commas inside each dimension, dimensions
    joined by ':'. The ORDER is the one from dimensionsMap (dim_index)."""
    return ":".join(",".join(str(c) for c in dim) for dim in selection_per_dim)


def cells(selection: list[list[int]]) -> int:
    """How many cells a selection asks for: the product of options per dimension."""
    total = 1
    for codes in selection:
        total *= len(codes)
    return total


def _payload(matrix, selection: list[list[int]]) -> dict:
    """The body of one POST to pivot, for a given selection."""
    return {
        "language": "ro",
        "encQuery": build_encquery(selection),
        "matCode": matrix.code,
        "matMaxDim": matrix.details.get("matMaxDim"),
        "matUMSpec": matrix.details.get("matUMSpec"),
    }


def _locality_index(matrix) -> int | None:
    """The position of the locality dimension, if the matrix has one."""
    for i, d in enumerate(matrix.dimensions):
        if d.role == "teritoriu" and territory.is_locality_dimension(
                d, matrix.details):
            return i
    return None


def _county_index(matrix, selection, loc_index: int, parents) -> int | None:
    """The position of the county dimension, the one holding the parentIds.

    FOM104D keeps county and locality as separate dimensions. When we fetch one
    county's localities we narrow the county dimension to that same county:
    otherwise we would ask for the product with all 43, almost all of it empty,
    and stay over the threshold.
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
    """Split a selection into pieces that each fit under the threshold.

    It cuts the dimension with the most options, into pieces sized by how much
    room the others leave. If even a single option piece does not fit, the
    recursion moves on to the next dimension. That makes every matrix
    downloadable, just in more requests.
    """
    if cells(selection) <= max_cells:
        return [selection]

    splittable = [i for i, codes in enumerate(selection) if len(codes) > 1]
    if not splittable:
        return [selection]          # a single cell, nothing left to cut

    i = max(splittable, key=lambda k: len(selection[k]))
    rest = max(1, cells(selection) // len(selection[i]))
    size = max(1, max_cells // rest)

    pieces = []
    for piece in split_options(selection[i], size):
        sub = list(selection)
        sub[i] = piece
        pieces.extend(split_selection(sub, max_cells))
    return pieces


def plan_requests(matrix, selection: list[list[int]],
                  max_cells: int | None = None) -> list[dict]:
    """Turn a per dimension selection into the list of POST payloads.

    Under the threshold, one payload. Over it, one per county for matrices with
    localities, otherwise a split on the largest dimension.
    """
    if max_cells is None:
        max_cells = MAX_CELLS
    if any(not codes for codes in selection):
        # an empty block would build an encQuery INS cannot read, and the
        # failure would surface far from the filter that caused it
        raise ValueError(
            "selection has an empty dimension; a filter matched nothing")
    if cells(selection) <= max_cells:
        return [_payload(matrix, selection)]

    loc_index = _locality_index(matrix)
    if loc_index is None:
        return [_payload(matrix, sel)
                for sel in split_selection(selection, max_cells)]

    loc_dim = matrix.dimensions[loc_index]
    requested = set(selection[loc_index])
    groups = territory.group_localities_by_county(loc_dim)
    county_index = _county_index(matrix, selection, loc_index, groups)

    payloads = []
    for parent, options in groups.items():
        ids = [o.nom_item_id for o in options if o.nom_item_id in requested]
        if not ids:
            continue

        base = list(selection)
        if county_index is not None and parent in selection[county_index]:
            base[county_index] = [parent]

        sel = list(base)
        sel[loc_index] = ids
        # a county that still does not fit is split further, on any dimension,
        # not just on localities
        for piece in split_selection(sel, max_cells):
            payloads.append(_payload(matrix, piece))
    return payloads
