"""Restricting a dimension to some of its options: the select= argument of get.

get() sends every option of every dimension, which is right for a first look
and wasteful once you know what you want: one age group out of eighteen still
costs the whole download. select= names a dimension and says which of its
options to keep, before the query is built, so the cell count, the chunking
strategy and the encQuery all work on the smaller set.

Nothing here touches the network. restrict() returns a copy of the matrix with
narrower dimensions and leaves the original alone, so the same Matrix can be
used again with a different select, or with none.
"""
import difflib
from dataclasses import replace


def _labels(dimensions) -> str:
    return ", ".join(repr(d.label.strip()) for d in dimensions)


def find_dimension(dimensions, key):
    """The one dimension a select key names, matched on its label.

    Exact match first, ignoring case and surrounding space, then a unique
    substring, so 'varsta' finds 'Grupe de varsta' without typing it out.
    Anything ambiguous is an error: quietly taking the first match would trim
    the wrong dimension, and the numbers would still look plausible.
    """
    if not isinstance(key, str):
        raise ValueError(
            f"select keys are dimension labels, as text; got {key!r}. "
            f"Available: {_labels(dimensions)}")

    want = key.strip().lower()
    matching = [d for d in dimensions if d.label.strip().lower() == want]
    if not matching:
        matching = [d for d in dimensions if want in d.label.strip().lower()]

    if len(matching) == 1:
        return matching[0]
    if len(matching) > 1:
        raise ValueError(
            f"select key {key!r} matches {len(matching)} dimensions: "
            f"{_labels(matching)}. Write the label in full.")
    raise ValueError(
        f"select key {key!r} matches no dimension of this indicator. "
        f"Available: {_labels(dimensions)}")


def _option_by_label(dimension, wanted: str):
    """The one option with this label. Anything else is an error, by name."""
    label = wanted.strip()
    hits = [o for o in dimension.options if o.label.strip() == label]
    if len(hits) == 1:
        return hits[0]

    where = f"select on {dimension.label.strip()!r}"
    if len(hits) > 1:
        raise ValueError(
            f"{where}: {wanted!r} matches {len(hits)} options; "
            f"name them by nomItemId instead")
    close = difflib.get_close_matches(
        label, [o.label.strip() for o in dimension.options], n=1)
    hint = f" Did you mean {close[0]!r}?" if close else ""
    raise ValueError(
        f"{where}: no option labelled {wanted!r}.{hint} "
        f"See m.options({dimension.label.strip()!r}).")


def choose_options(dimension, chooser) -> list:
    """Which options of one dimension to keep, from one select value.

    Three forms, and a single value stands for a list of one:
    whole numbers are nomItemIds, text is matched against option labels, and a
    callable is a predicate on the option. The result keeps the dimension's own
    order, the order INS gave, whatever order they were asked for in.
    """
    where = f"select on {dimension.label.strip()!r}"

    if callable(chooser):
        kept = [o for o in dimension.options if chooser(o)]
        if not kept:
            raise ValueError(
                f"{where}: the predicate kept none of the "
                f"{len(dimension.options)} options")
        return kept

    values = (list(chooser) if isinstance(chooser, (list, tuple, set, frozenset))
              else [chooser])
    if not values:
        raise ValueError(f"{where}: nothing chosen, the list is empty")

    known = {o.nom_item_id for o in dimension.options}
    keep = set()
    for value in values:
        # bool is an int in Python, and True is not a nomItemId
        if isinstance(value, int) and not isinstance(value, bool):
            if value not in known:
                raise ValueError(
                    f"{where}: no option with nomItemId {value}. "
                    f"See m.options({dimension.label.strip()!r}).")
            keep.add(value)
        else:
            keep.add(_option_by_label(dimension, str(value)).nom_item_id)

    return [o for o in dimension.options if o.nom_item_id in keep]


def restrict(matrix, select: dict):
    """A copy of the matrix whose named dimensions carry only the chosen options.

    Everything downstream reads its options from the dimensions, so restricting
    them here is enough: the cell count, the chunking, the encQuery and the
    standardization all see the smaller set with no further change. Dimensions
    select does not name are left whole.
    """
    if not isinstance(select, dict):
        raise ValueError(
            "select is a dict of {dimension label: options}, where options is "
            "a list of nomItemIds, a list of option labels, or a predicate on "
            "the option, for example select={'Sexe': ['Masculin']}")

    narrowed = {}
    for key, chooser in select.items():
        dimension = find_dimension(matrix.dimensions, key)
        if dimension.dim_index in narrowed:
            raise ValueError(
                f"select names the dimension {dimension.label.strip()!r} "
                f"twice, through two different keys")
        narrowed[dimension.dim_index] = choose_options(dimension, chooser)

    return replace(matrix, dimensions=[
        replace(d, options=narrowed[d.dim_index])
        if d.dim_index in narrowed else d
        for d in matrix.dimensions])


def summary(original, restricted) -> list[str]:
    """One line per trimmed dimension, for the decision printout of get()."""
    lines = []
    for before, after in zip(original.dimensions, restricted.dimensions):
        if len(after.options) != len(before.options):
            lines.append(
                f"  select: {before.label.strip()} limited to "
                f"{len(after.options)} of {len(before.options)} options")
    return lines
