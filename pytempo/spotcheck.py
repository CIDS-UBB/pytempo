"""Picking a few units at random and saying how to check them by hand.

A download can be complete, joined correctly and still be wrong about what it
means: the wrong option pinned, the wrong dimension read, a series that is not
the one you thought you asked for. No amount of internal checking catches that.
The only thing that does is opening TEMPO Online and reading the same number
off the site.

What makes that tedious is not the comparison, it is the setup: finding one
locality among three thousand, and knowing which option every other dimension
has to be on for the site to show a single series. So this does the setup. It
picks units at random, pins every inner dimension on its total, and prints the
series ready to be read against the screen.

It touches nothing and fetches nothing: it reads the frame you already have.
"""
import random

from . import endpoints, territory
from .parse import VALUE_COLUMN


def _distinct(values) -> list:
    """The distinct values, in the order the frame has them."""
    return list(dict.fromkeys(values))


def _pin(values) -> tuple:
    """Which option to fix a dimension on: its total, or the first it has.

    The total is what makes a single readable series on the site. A dimension
    with no total, and there are plenty, gets its first option and says so:
    a pinned dimension the reader does not know about is how a spot check ends
    up comparing two different things.
    """
    for value in values:
        if territory.is_total_label(str(value)):
            return value, True
    return (values[0] if values else None), False


def choose_units(df, unit_key, n: int, seed=None) -> list:
    """n distinct units picked at random, out of those that carry a value.

    seed makes the choice reproducible, which is what turns a spot check into
    something you can put in a script and rerun after a change.
    """
    with_data = unit_key[df[VALUE_COLUMN].notna()].dropna()
    units = _distinct(with_data.tolist())
    if not units:
        raise ValueError(
            "no row carries a value, so there is nothing to check by hand")
    return random.Random(seed).sample(units, min(n, len(units)))


def _pins_for(rows, internal: list[str]) -> tuple:
    """Fix every inner dimension, narrowing the rows as it goes.

    Each dimension is pinned on what is still available after the previous
    ones, so the result is never an empty series through a combination that
    does not exist.
    """
    pinned = []
    for column in internal:
        values = _distinct(rows[column].dropna().tolist())
        value, is_total = _pin(values)
        if value is None:
            continue
        pinned.append((column, value, is_total, len(values)))
        rows = rows[rows[column] == value]
    return rows, pinned


def _label_for(rows, unit_base: str, context: list[str]) -> str:
    """One line naming the unit: its name, its county, its SIRUTA."""
    first = rows.iloc[0]
    parts = [str(first[unit_base]).strip()]
    for column in context:
        parts.append(f"[{column}: {str(first[column]).strip()}]")
    siruta = f"{unit_base}_siruta"
    if siruta in rows.columns and first[siruta] is not None:
        parts.append(f"siruta {first[siruta]}")
    return "  ".join(parts)


def report(df, unit_key, unit_base: str, year_col: str, internal: list[str],
           context: list[str], n: int = 1, seed=None) -> None:
    """Print the targets, what was pinned on each, and the series to compare."""
    units = choose_units(df, unit_key, n, seed)
    total_units = len(_distinct(unit_key.dropna().tolist()))

    seed_text = f", seed {seed}" if seed is not None else ""
    print(f"spot check: {len(units)} of {total_units} units{seed_text}")

    for i, unit in enumerate(units, 1):
        rows = df[(unit_key == unit) & df[VALUE_COLUMN].notna()]
        print(f"  {i}. {_label_for(rows, unit_base, context)}")

        rows, pinned = _pins_for(rows, internal)
        for column, value, is_total, seen in pinned:
            note = "" if is_total else f"   (no total among its {seen} values)"
            print(f"     fixed {column} = {str(value).strip()}{note}")

        series = rows[[year_col, VALUE_COLUMN]].sort_values(year_col)
        print(f"     {len(series)} years:")
        for year, value in series.itertuples(index=False):
            print(f"       {year}  {value}")
        if len(series) != series[year_col].nunique():
            print("     more rows than years: a dimension is still not pinned, "
                  "so this is several series at once")

    print(f"  read the same numbers at {endpoints.site()}")
    print("  open the same indicator, pick the same options, compare year "
          "by year")
    print("  a year missing here is a ':' on the site, not a zero")
