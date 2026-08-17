"""The menu how() prints: what this indicator lets you choose, and the calls.

how() used to say how to download an indicator. What it could not say is what
there is to choose, which is the thing a reader does not know: that POP107D has
104 ages in 19 groups, that its territory reaches 3181 localities, that Sexe has
three options and one of them is the total. Without that, select= and level= are
arguments you can only use once you already know the answer.

So everything here is read off the loaded dimensions, per indicator, and printed
as calls that run as they stand. Nothing is hardcoded per code, and no numbers
are guessed: the option counts come from the options, the request counts from
planning the download, the groups and leaves from the same hierarchy detection
select= uses.

Printing only. The decisions live in Matrix; this module writes them down.
"""
from . import hierarchy, territory


def download_line(cod: str, wanted, select_key: str | None = None,
                  kind: str = "groups") -> str:
    """A download() call for this indicator, ready to copy.

    It carries the level actually being asked for, not a generic example: a
    command that has to be edited before it runs is a command nobody runs.
    """
    parts = []
    if wanted and len(list(wanted)) == 1:
        parts.append(f"level={list(wanted)[0]!r}")
    elif wanted:
        parts.append(f"levels={list(wanted)!r}")
    if select_key:
        parts.append(f"select={{{select_key!r}: {kind!r}}}")
    parts.append(f"folder='data/{cod.lower()}'")
    return f"m.download({', '.join(parts)})"


def get_line(wanted, select_key: str | None = None,
             kind: str = "groups") -> str:
    """The same call through get(), for an indicator that fits in memory."""
    parts = []
    if wanted and len(list(wanted)) == 1:
        parts.append(f"level={list(wanted)[0]!r}")
    elif wanted:
        parts.append(f"levels={list(wanted)!r}")
    if select_key:
        parts.append(f"select={{{select_key!r}: {kind!r}}}")
    return f"m.get({', '.join(parts)})"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def dimension_units(dimension, details: dict) -> dict:
    """How many units one territorial dimension holds, per level.

    A confirmed locality dimension stands for one level, so its options are
    counted as localities, without the total, which is not a locality. A
    hierarchical one is counted by reading the level of each option name.
    """
    if territory.is_locality_dimension(dimension, details):
        return {"localitate": sum(1 for o in dimension.options
                                  if not territory.is_total_label(o.label))}
    counts = {}
    for option in dimension.options:
        level = territory.option_level(option.label)
        counts[level] = counts.get(level, 0) + 1
    return counts


def units_per_level(matrix) -> dict:
    """The whole indicator's units per level, across its territorial
    dimensions."""
    counts = {}
    for dimension in matrix.dimensions:
        if dimension.role != "teritoriu":
            continue
        for level, n in dimension_units(dimension, matrix.details).items():
            counts[level] = counts.get(level, 0) + n
    return counts


def filterable(matrix) -> list:
    """The dimensions select= is for: not territory, not time, not the unit.

    Territory has level= and time is usually wanted whole. What is left is
    where a filter changes what you get: sex, age, activity, category.
    """
    return [d for d in matrix.dimensions
            if d.role not in ("teritoriu", "timp", "um")]


def biggest_hierarchy(matrix):
    """The hierarchical dimension worth trimming first, or None."""
    hierarchical = [d for d in filterable(matrix)
                    if hierarchy.is_hierarchical(d)]
    if not hierarchical:
        return None
    return max(hierarchical, key=lambda d: len(d.options))


def print_levels(matrix, default_level, polite: int) -> None:
    """What level= takes here, how big each level is, and what it costs.

    The request count per level is the useful part: it is the difference
    between a call that answers in a second and one get() will refuse, and it
    is why the call printed next to a level is get() for some and download()
    for others.
    """
    levels = matrix.levels
    counts = units_per_level(matrix)
    width = max(len(level) for level in levels)

    print()
    print("  TERRITORIAL LEVEL, what level= takes here:")
    for level in levels:
        units = counts.get(level, 0)
        requests = matrix._requests_for([level])
        call = (get_line([level]) if requests <= polite
                else download_line(matrix.code, [level]))
        note = "   the finest, and the default" if level == default_level else ""
        print(f"    {level:<{width}}  {_plural(units, 'unit'):>12}, "
              f"{_plural(requests, 'request'):>13}   {call}{note}")
    print(f"    {'every level at once':<{width + 29}}   m.get(level=None)")


def _print_hierarchical(dimension) -> None:
    label = dimension.label.strip()
    print(f"    {label}, hierarchical, {len(dimension.options)} options")

    lines = []
    for kind in ("total", "groups", "leaves"):
        try:
            kept = hierarchy.pick(dimension, kind)
        except ValueError:
            continue
        lines.append((f"select={{{label!r}: {kind!r}}}",
                      _plural(len(kept), "option")))
    width = max((len(call) for call, _ in lines), default=0)
    for call, count in lines:
        print(f"      {call:<{width}}   {count}")
    print(f"      m.options({label!r}, kind='groups') lists them")


def _print_flat(dimension, big_dimension: int) -> None:
    label = dimension.label.strip()
    n = len(dimension.options)
    if n > big_dimension:
        print(f"    {label}, flat, {n} options, too many to list here")
        print(f"      m.options({label!r}) shows them")
        print(f"      select={{{label!r}: ['...']}}")
        return

    shown = ", ".join(o.label.strip() for o in dimension.options[:3])
    more = ", ..." if n > 3 else ""
    print(f"    {label}, flat, {n} options: {shown}{more}")
    example = next((o for o in dimension.options
                    if not territory.is_total_label(o.label)),
                   dimension.options[0])
    print(f"      select={{{label!r}: [{example.label.strip()!r}]}}")


def print_filters(matrix, big_dimension: int) -> None:
    """One entry per dimension a filter can narrow, with the calls that do it.

    A hierarchical dimension gets the keywords and what each of them keeps,
    never the full list: 104 ages on screen help nobody, and m.options() is one
    line away. A flat one gets its first few values, which is usually enough to
    recognize the rest.
    """
    dimensions = filterable(matrix)
    print()
    if not dimensions:
        print("  FILTERS: none to add. This indicator is territory and time "
              "only, so")
        print("  level= is the whole choice.")
        return

    print(f"  FILTERS, what select= takes here "
          f"({_plural(len(dimensions), 'dimension')}):")
    for dimension in dimensions:
        if hierarchy.is_hierarchical(dimension):
            _print_hierarchical(dimension)
        else:
            _print_flat(dimension, big_dimension)


def print_example(matrix, default_level, polite: int) -> None:
    """One call that puts it together: the finest level, the useful filter.

    The filter chosen is the groups of the largest hierarchy, because that is
    the one that turns an unreasonable download into a reasonable one. Which of
    get() and download() it uses is decided by planning that exact call, not by
    the indicator's size in general: a filter can bring a large one back under
    the line.
    """
    wanted = [default_level] if default_level else []
    hierarchical = biggest_hierarchy(matrix)
    key = hierarchical.label.strip() if hierarchical else None
    select = {key: "groups"} if key else None
    requests = matrix._requests_for(wanted, select)

    print()
    print("  A TYPICAL CALL for this indicator:")
    if requests > polite:
        print(f"    {download_line(matrix.code, wanted, key)}")
    else:
        print(f"    {get_line(wanted, key)}")
    if key:
        groups = len(hierarchy.pick(hierarchical, "groups"))
        print(f"    {_plural(requests, 'request')}: {groups} of the "
              f"{len(hierarchical.options)} options of {key}, everything "
              f"else whole")
    else:
        print(f"    {_plural(requests, 'request')}, nothing filtered out")
