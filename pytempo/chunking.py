"""Building the query and splitting large requests. Ported from the R package.

Locality level matrices do not fit in a single POST: FOM104D has 43 counties
and 3183 localities, which is millions of cells. They are downloaded county by
county, using parentId, which ties a locality to its county, and if a single
county is still too large its selection is split further.

The same idea serves a hierarchy that INS splits across several dimensions,
such as the five CAEN Rev.1 dimensions of INT109B: fix the path, ask for the
children. Without it they are multiplied as if independent, and INT109B plans
9,127,800 requests instead of 283.

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


def _is_own_total(option) -> bool:
    """A Total inside a chain points at itself: that is how INS marks it."""
    return option.parent_id == option.nom_item_id


def _links_completely(parent, child) -> bool:
    """Does every option of child, its Total aside, point at an option of parent?

    Complete or nothing: a chain linked halfway would plan requests that miss
    the options left unlinked, and missing data in silence is the one thing the
    package never does.
    """
    ids = {o.nom_item_id for o in parent.options}
    linked = [o for o in child.options if not _is_own_total(o)]
    return bool(linked) and all(o.parent_id in ids for o in linked)


def find_chain(matrix) -> list[int] | None:
    """Positions of dimensions that form one hierarchy split across several.

    INT109B keeps CAEN Rev.1 in five dimensions, section, subsection,
    division, group and class, each option pointing through parentId at its
    parent in the dimension before. Multiplying them as if they were
    independent asks for 877 billion cells, almost all of them combinations
    that cannot exist, a class of retail under the section for mining.

    A chain is two or more consecutive dimensions, each linked completely to
    the one before, each below the first carrying its own Total, which is how
    INS writes an aggregate: the path down to a node, then Total. The
    locality dimension is left out, its county link has a branch of its own.
    None when there is no chain.
    """
    dims = matrix.dimensions
    loc = _locality_index(matrix)
    for start in range(len(dims) - 1):
        chain = [start]
        while (chain[-1] + 1 < len(dims) and chain[-1] + 1 != loc
               and _links_completely(dims[chain[-1]], dims[chain[-1] + 1])):
            chain.append(chain[-1] + 1)
        if len(chain) > 1 and start != loc:
            if all(any(_is_own_total(o) for o in dims[k].options)
                   for k in chain[1:]):
                return chain
    return None


def chain_selections(matrix, selection: list[list[int]],
                     chain: list[int]) -> list[list[list[int]]]:
    """One selection per node with children: the path fixed, the children asked.

    The roots come first, with every dimension below them on its Total, then
    level by level, in the order INS lists the options, the children of each
    node, with the path above it fixed and the levels below on Total. Only
    what the selection allows: a node outside it, or a Total below it that the
    selection left out, is not asked for, exactly as the plain product would
    not have asked for it.
    """
    dims = matrix.dimensions
    allowed = [set(codes) for codes in selection]
    totals = {k: next(o.nom_item_id for o in dims[k].options if _is_own_total(o))
              for k in chain[1:]}
    children = {}
    for depth, k in enumerate(chain):
        for o in dims[k].options:
            if depth and not _is_own_total(o):
                children.setdefault((depth - 1, o.parent_id), []).append(o)

    def below_on_total(sel, depth):
        for k in chain[depth + 1:]:
            if totals[k] not in allowed[k]:
                return None
            sel[k] = [totals[k]]
        return sel

    out = []
    roots = [o.nom_item_id for o in dims[chain[0]].options
             if o.nom_item_id in allowed[chain[0]]]
    if roots:
        sel = list(selection)
        sel[chain[0]] = roots
        sel = below_on_total(sel, 0)
        if sel is not None:
            out.append(sel)

    # the path to every node, so a node's children are asked under exactly it
    paths = {(0, r): [r] for r in roots}
    for depth in range(len(chain) - 1):
        for o in dims[chain[depth]].options:
            path = paths.get((depth, o.nom_item_id))
            if path is None:
                continue
            kids = [c.nom_item_id for c in children.get((depth, o.nom_item_id), [])
                    if c.nom_item_id in allowed[chain[depth + 1]]]
            if not kids:
                continue
            for c in kids:
                paths[(depth + 1, c)] = path + [c]
            sel = list(selection)
            for d, node in enumerate(path):
                sel[chain[d]] = [node]
            sel[chain[depth + 1]] = kids
            sel = below_on_total(sel, depth + 1)
            if sel is not None:
                out.append(sel)
    return out


def chain_summary(matrix) -> dict | None:
    """What the registry keeps about a chain: its dimensions and its cost.

    The registry is computed from records, not from metadata, so the number of
    requests has to be counted while the metadata is at hand: one node per
    request is a fact about the tree, not about the option counts.
    """
    chain = find_chain(matrix)
    if chain is None:
        return None
    full = [[o.nom_item_id for o in d.options] for d in matrix.dimensions]
    return {"dims": [matrix.dimensions[k].label.strip() for k in chain],
            "requests": len(plan_requests(matrix, full))}


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
    localities; for dimensions chained through parentId, one per node with
    children (find_chain); otherwise a split on the largest dimension.
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
        chain = find_chain(matrix)
        if chain is not None:
            # each node's children, the path fixed; a node with too many
            # children, or large other dimensions, is still split as usual
            return [_payload(matrix, piece)
                    for sel in chain_selections(matrix, selection, chain)
                    for piece in split_selection(sel, max_cells)]
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
