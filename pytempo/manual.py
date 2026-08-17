"""The menu how() prints: what this indicator lets you choose, and the calls.

how() used to say how to download an indicator. What it could not say is what
there is to choose, which is the thing a reader does not know: that POP107D has
104 ages in 19 groups, that its territory reaches 3181 localities, that Sexe has
three options and one of them is the total. Without that, select= and level= are
arguments you can only use once you already know the answer.

Being right was not enough, though. On TUR101B the old block printed
'Tipuri de structuri de primire turistica' four times, once per select line,
and said 'groups: 17 options' without a word about what those seventeen are.
Everything was there and nothing was easy. So: the call to copy comes first,
each dimension is named once in full and then by a short name you can type,
counts come with two or three real values next to them, and the reason the
suggested call has the shape it has is written out in words.

Everything is read off the loaded dimensions, per indicator. Nothing is
hardcoded per code, and no numbers are guessed: the option counts come from the
options, the request counts from planning the download, the groups and leaves
from the same hierarchy detection select= uses, the short names from the same
resolver select= uses to accept them.

Printing only. The decisions live in Matrix; this module writes them down.
"""
import textwrap

from . import hierarchy, selection, territory


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


def _shorten(text: str, room: int) -> str:
    """Cut a long name at a word, not mid syllable: 'Statiuni din zona e...'
    reads like a bug rather than like a name that was too long."""
    if len(text) <= room:
        return text
    cut = text[:room - 3]
    if " " in cut.strip():
        cut = cut[:cut.rstrip().rfind(" ")]
    return cut.rstrip(" ,") + "..."


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


def alias_for(matrix, dimension) -> str:
    """A short name for a dimension: the one you would actually type.

    'Tipuri de structuri de primire turistica' written out four times, once per
    select line, is most of what made the old block tiring. select= has always
    accepted any part of a label that names one dimension and no other, so a
    short name was already there; it was simply never shown.

    The first word long enough to be distinctive wins, because that is the head
    noun and the one a reader reaches for. Each candidate is checked through
    the resolver select= itself uses, so a name printed here always resolves to
    the dimension it was printed for, and the full label is the fallback when
    nothing shorter is unambiguous.
    """
    label = dimension.label.strip()
    for word in [w.strip(" ,.:()") for w in label.split()]:
        if len(word) < 4:
            continue
        try:
            if selection.find_dimension(matrix.dimensions, word) is dimension:
                return word.lower()
        except ValueError:
            continue
    return label


def _values(options, room: int = 3) -> str:
    """A few real option names, so that a count stops being only a count.

    '17 options' says nothing about what they are. Naming three of them turns
    the line into something a reader recognises, and it is also how a wrong
    guess about the levels becomes visible at a glance.
    """
    shown = [_shorten(o.label.strip(), 32) for o in options[:room]]
    if len(options) > room:
        shown.append("...")
    return ", ".join(shown)


def print_headline(matrix) -> None:
    """The code and what it measures, before any of the mechanics."""
    print(f"How to download {matrix.code}")
    for line in textwrap.wrap(" ".join(matrix.name.split()), 72):
        print(f"  {line}")


def recommended(matrix, default_level) -> tuple:
    """The call worth suggesting, and the reasons it has that shape.

    Every option of every dimension is the default, and on an indicator with
    three of them that is a cross tabulation nobody asked for. The suggestion
    varies one dimension, the largest hierarchy, and puts the others on their
    total: the shape most people want first, and the smallest download that
    answers anything.
    """
    varying = biggest_hierarchy(matrix)
    select, reasons = {}, []

    if varying is not None:
        key = alias_for(matrix, varying)
        select[key] = "groups"
        kept = len(hierarchy.pick(varying, "groups"))
        reasons.append(f"'groups' on {key} keeps the {kept} aggregates and "
                       f"leaves out the finer breakdown under them")

    pinned = []
    for dimension in filterable(matrix):
        if dimension is varying:
            continue
        if any(territory.is_total_label(o.label) for o in dimension.options):
            pinned.append(alias_for(matrix, dimension))
    for key in pinned:
        select[key] = "total"
    if pinned:
        reasons.append(f"'total' on {' and '.join(pinned)}, since a breakdown "
                       f"you did not ask for multiplies the rows without "
                       f"adding an answer")
    return select, reasons


def _call_text(matrix, wanted, select, requests: int, polite: int) -> str:
    parts = []
    if wanted:
        parts.append(f"level={wanted[0]!r}")
    if select:
        inner = ", ".join(f"{k!r}: {v!r}" for k, v in select.items())
        parts.append(f"select={{{inner}}}")
    if requests > polite:
        parts.append(f"folder='data/{matrix.code.lower()}'")
        return f"m.download({', '.join(parts)})"
    return f"m.get({', '.join(parts)})"


def print_call(matrix, default_level, polite: int,
               whole: int | None = None) -> None:
    """The one call to copy, first, with the reason for its shape in words.

    When the indicator is too large for get() and this call is not, the two
    numbers side by side are the lesson: the filter is what turns a download
    into a request.
    """
    select, reasons = recommended(matrix, default_level)
    wanted = [default_level] if default_level else []
    requests = matrix._requests_for(wanted, select or None)

    print()
    print("  THE CALL, ready to copy:")
    print(f"    {_call_text(matrix, wanted, select, requests, polite)}")
    if whole and whole > polite >= requests:
        print(f"    {_plural(requests, 'request')}, not the {whole} the whole "
              f"indicator costs: that is what the filter buys")
    else:
        print(f"    {_plural(requests, 'request')}")
    if not reasons:
        return
    print()
    said = "Why this shape: " + ", and ".join(reasons) + \
        ". Change any of it below."
    for line in textwrap.wrap(said, 70):
        print(f"    {line}")


def print_levels(matrix, default_level, polite: int) -> None:
    """The territorial levels, as a menu: you pick exactly one.

    The request count per level is the useful part: it is the difference
    between a call that answers in a second and one get() will refuse, and it
    is why the call next to a level is get() for some and download() for others.
    """
    levels = matrix.levels
    counts = units_per_level(matrix)
    width = max(len(level) for level in levels)

    print()
    print("  TERRITORIAL LEVEL, pick one:")
    for level in levels:
        units = counts.get(level, 0)
        requests = matrix._requests_for([level])
        call = (get_line([level]) if requests <= polite
                else download_line(matrix.code, [level]))
        note = "   default, the finest" if level == default_level else ""
        print(f"    {level:<{width}}  {_plural(units, 'unit'):>12}, "
              f"{_plural(requests, 'request'):>13}   {call}{note}")
    print(f"    {'every level at once':<{width + 29}}   m.get(level=None)")


def _print_filter(matrix, dimension, big_dimension: int, width: int) -> None:
    """One dimension: the short name, the real name, and what you can say."""
    key = alias_for(matrix, dimension)
    pad = " " * (width + 6)

    print()
    print(f"    {key:<{width}}  {dimension.label.strip()}")
    if hierarchy.is_hierarchical(dimension):
        levels = len(set(hierarchy.depths(dimension).values()))
        print(f"{pad}{len(dimension.options)} options on {levels} levels")
        for kind in ("groups", "leaves", "total"):
            kept = hierarchy.pick(dimension, kind)
            print(f"{pad}{kind!r:<9}{len(kept):>4}: {_values(kept)}")
        return

    print(f"{pad}{len(dimension.options)} options, one level")
    if len(dimension.options) <= big_dimension:
        print(f"{pad}values: {_values(dimension.options)}")
    else:
        print(f"{pad}too many to list here, see m.options({key!r})")
    example = next((o for o in dimension.options
                    if not territory.is_total_label(o.label)),
                   dimension.options[0])
    print(f"{pad}a few:  select={{{key!r}: [{example.label.strip()!r}]}}")
    if any(territory.is_total_label(o.label) for o in dimension.options):
        print(f"{pad}or one: select={{{key!r}: 'total'}}")


def print_filters(matrix, big_dimension: int) -> None:
    """The optional filters, one block each, named by what you would type."""
    dimensions = filterable(matrix)
    print()
    if not dimensions:
        print("  FILTERS: none to add. This indicator is territory and time "
              "only,")
        print("  so the level above is the whole choice.")
        return

    print("  FILTERS, all optional. The short name on the left is what you "
          "write:")
    width = max(len(alias_for(matrix, d)) for d in dimensions)
    for dimension in dimensions:
        _print_filter(matrix, dimension, big_dimension, width)


def print_more(matrix, full: bool) -> None:
    """Where the rest is, for whoever wants it."""
    keys = [alias_for(matrix, d) for d in filterable(matrix)]
    lines = []
    if keys:
        lines.append((f"m.options({keys[0]!r})",
                      "every option of one of them, in full"))
    lines.append(("m.get(raw=True)", "exactly what INS returns, no extras"))
    if not full:
        lines.append(("m.how(full=True)", "the plan, the strategy, the rest"))

    print()
    width = max(len(call) for call, _ in lines)
    for call, what in lines:
        print(f"  {call:<{width}}   {what}")


def print_too_large(matrix, request_count: int, wanted, polite: int) -> None:
    """The guidance get() prints when it stops on an indicator this large.

    It is a section of the manual, not an error message. The stopping is right,
    the wall of text inside an exception was not: in a notebook it came out
    under 'Traceback (most recent call last)', with a file and a line number,
    so being told what to do next looked like something crashing. Printed first
    and formatted, it reads as what it is, and the exception that follows it is
    one line.
    """
    print()
    print(f"{matrix.code} IS TOO LARGE FOR get(). Nothing has been "
          f"downloaded.")
    print(f"  {request_count} requests, over the {polite} get() will hold in "
          f"memory. get() keeps")
    print("  every one of them until the last comes back, so a single late "
          "timeout,")
    print("  and INS does time out, loses all of it with nothing to resume "
          "from.")
    print()
    print("  Use download() instead, which is the same call through disk:")
    print(f"    {download_line(matrix.code, wanted)}")
    print("  It writes each request as it arrives, resumes where it stopped, "
          "and")
    print("  retries on timeout.")
    print()
    print(f"  m.how()                the whole menu for {matrix.code}: every "
          f"level, every filter")
    print("  m.get(confirm=False)   go ahead with get() anyway, in memory, "
          "no checkpoint")
    print()
