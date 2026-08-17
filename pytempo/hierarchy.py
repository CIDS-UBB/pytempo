"""Which options of a dimension are aggregates and which are the leaves.

Asking for the 19 age groups of POP107D and not the 85 single ages is a common
need, and up to now it meant writing a loop over the labels: keep the ones with
a hyphen, or the one that says Total, or the one that says si peste. That is a
guess about how INS writes names, it breaks on the next dimension, and it says
nothing about structure.

WHAT THE DATA ACTUALLY CARRIES, measured before writing any of this:

    parentId          populated ONLY on locality dimensions, where it points at
                      the county, that is at an option of a DIFFERENT dimension.
                      Null on every other dimension measured: POP107D and
                      POP105A ages (0 of 104), FOM104F CAEN (0 of 68), SCL101B
                      levels of education (0 of 18), AGR101A land use (0 of 14),
                      and even the hierarchical territory of SCL101B, macroregion
                      plus region plus county (0 of 55).
    offset            a plain 1, 2, 3 running order on those dimensions. No
                      depth in it.
    details           carries dimension roles and flags, nothing about the tree
                      inside a dimension.
    label indentation three leading spaces per level, and it is the only signal
                      left: 'Total', '   0- 4 ani', '      0 ani'. INS renders
                      the tree in its own web interface from exactly this.

So parentId is read first, because it is explicit and it is what a fixture or a
future response with real links would carry, and indentation second, because it
is what the live catalogue actually has today. Indentation is a layout signal,
not a naming pattern: it says nothing about what the option is called, only
about where it sits, which is why it survives dimensions this module has never
seen. It is still a fallback, and if INS ever stops indenting, the keywords
report a flat dimension rather than guessing.

A dimension with no signal at all, and there are many, CAEN Rev.2 among them,
is flat as far as anyone can tell, and asking for its groups is an error that
says so.
"""
from . import territory

# what select= and options(kind=) accept
KINDS = ("groups", "parents", "leaves", "total")


def _indent(label) -> int:
    """How far the label is pushed in. Whitespace, not a particular character."""
    text = label or ""
    return len(text) - len(text.lstrip())


def _from_parent_ids(dimension) -> dict | None:
    """Depth per option, from parentId, when the links stay inside the
    dimension.

    A link to an option of another dimension is not a hierarchy of this one:
    a locality pointing at its county says something true about the territory
    and nothing about the locality dimension's own shape. A self reference,
    which the locality TOTAL carries, is not a link either.
    """
    known = {o.nom_item_id for o in dimension.options}
    parent_of = {}
    for option in dimension.options:
        parent = option.parent_id
        if parent is None or parent == option.nom_item_id or parent not in known:
            continue
        parent_of[option.nom_item_id] = parent
    if not parent_of:
        return None

    depths = {}
    for option in dimension.options:
        depth, walk = 0, option.nom_item_id
        # a malformed loop would spin here, so the walk is bounded by the
        # number of options, which is as deep as a tree of them can be
        while walk in parent_of and depth <= len(known):
            walk = parent_of[walk]
            depth += 1
        depths[option.nom_item_id] = depth
    return depths


def _from_indentation(dimension) -> dict | None:
    """Depth per option, from how far each label is indented.

    The widths are ranked rather than divided: three spaces per level is what
    INS uses, but ranking the distinct widths works whatever the step is.
    """
    widths = sorted({_indent(o.label) for o in dimension.options})
    if len(widths) < 2:
        return None
    depth_of = {width: rank for rank, width in enumerate(widths)}
    return {o.nom_item_id: depth_of[_indent(o.label)]
            for o in dimension.options}


def depths(dimension) -> dict | None:
    """How deep each option sits, or None when the dimension is flat."""
    return _from_parent_ids(dimension) or _from_indentation(dimension)


def is_hierarchical(dimension) -> bool:
    """True when this dimension has aggregates and leaves to tell apart."""
    return depths(dimension) is not None


def _totals(dimension) -> list:
    return [o for o in dimension.options
            if territory.is_total_label(o.label)]


def _flat_error(dimension, kind: str) -> ValueError:
    return ValueError(
        f"select {kind!r} on {dimension.label.strip()!r}: this dimension is "
        f"not hierarchical, its {len(dimension.options)} options are all at "
        f"the same level, so there are no groups to keep and no leaves to "
        f"drop. Name the options you want, as labels or as nomItemIds, or "
        f"pass a predicate. See m.options({dimension.label.strip()!r}).")


def pick(dimension, kind: str) -> list:
    """The options of one kind, in the order the dimension has them.

    A kind is a LEVEL, not a count of children: leaves are the options at the
    finest level the dimension reaches, groups are everything above it. The
    obvious alternative, calling an option a group when something sits under
    it, is wrong twice over on real data, and both cases are in the fixtures:

    POP107D's '85 ani si peste' has no single ages under it, since INS does not
    list ages past 85 one by one. By children it would be a leaf, and asking
    for the age groups would give 18 of the 19 that exist, silently missing the
    oldest one.

    AGR101A's 'Alte suprafete' has nothing under it either, and it sits next to
    'Agricola' and 'Terenuri neagricole total', which do. By children the groups
    would be Total plus those two, and they do not add up to the total: anyone
    computing a share of land use would be quietly short of a category.

    By level both come out right, because both are written at the level of the
    aggregates, which is what they are.
    """
    wanted = str(kind).strip().lower()
    if wanted not in KINDS:
        raise ValueError(
            f"unknown selection kind {kind!r}. Available: "
            f"{', '.join(KINDS)}")

    if wanted == "total":
        totals = _totals(dimension)
        if not totals:
            raise ValueError(
                f"select 'total' on {dimension.label.strip()!r}: this "
                f"dimension has no total option. See "
                f"m.options({dimension.label.strip()!r}).")
        return totals

    levels = depths(dimension)
    if levels is None:
        raise _flat_error(dimension, wanted)
    finest = max(levels.values())

    if wanted in ("groups", "parents"):
        kept = [o for o in dimension.options
                if levels[o.nom_item_id] < finest
                or territory.is_total_label(o.label)]
    else:
        kept = [o for o in dimension.options
                if levels[o.nom_item_id] == finest
                and not territory.is_total_label(o.label)]

    if not kept:
        raise ValueError(
            f"select {wanted!r} on {dimension.label.strip()!r}: none of its "
            f"{len(dimension.options)} options are of that kind")
    return kept
