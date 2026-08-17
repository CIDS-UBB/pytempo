"""Turn the CSV from pivot into a long format DataFrame.

Format measured on a real response (FOM101A): comma delimiter with one space
after each field, decimal point, no quoting anywhere, \\n line endings, utf-8
with no BOM. One column per dimension, in dimensionsMap order, plus the value
column at the end.

Two traps, both confirmed against real data:

The header is not a trustworthy source of names. INS replaces commas inside a
dimension label with spaces, so 'Macroregiuni, regiuni de dezvoltare si judete'
arrives as 'Macroregiuni  regiuni de dezvoltare si judete'. Names are taken from
matrix.dimensions, in order, not from the header.

The CSV is sparse. Combinations with no data are absent as whole rows, not
present as blanks, for real administrative reasons (Ilfov did not exist before
1996). So we do not validate on row counts and do not assume a complete grid.
"""
import io
import re

import pandas as pd

from . import territory

VALUE_COLUMN = "Valoare"

_YEAR = re.compile(r"\b(\d{4})\b")


class EmptyResponse(ValueError):
    """pivot answered with nothing at all, which is the server, not the data.

    A ValueError, so anything catching one keeps working, and download() treats
    it like any other failed slice: reported at the end, asked for again on the
    next run.
    """


def pivot_csv_to_dataframe(csv_text: str, matrix) -> pd.DataFrame:
    """Raw CSV from pivot into a long format DataFrame.

    The column count is the safety net: the comma delimiter only works because
    INS strips commas out of labels, and that is not guaranteed.
    """
    if not (csv_text or "").strip():
        # not a CSV with no rows, which is legitimate and handled below, but
        # nothing at all: pivot answered 200 with an empty body. Observed on
        # the live server, for well formed requests that returned data the day
        # before. Left to pandas it surfaces as EmptyDataError, no columns to
        # parse from file, which names neither the cause nor the cure
        raise EmptyResponse(
            f"{matrix.code}: INS answered with an empty body, not with data. "
            f"The request was well formed, so this is the server having a bad "
            f"moment rather than a combination with no data, which comes back "
            f"as a CSV with a header and no rows. Try again later; inside "
            f"download() this costs one slice, which resume asks for again.")

    df = pd.read_csv(
        io.StringIO(csv_text),
        sep=",",
        skipinitialspace=True,
        decimal=".",
    )

    expected = len(matrix.dimensions) + 1
    if df.shape[1] != expected:
        raise ValueError(
            f"CSV has {df.shape[1]} columns, expected {expected} "
            f"({len(matrix.dimensions)} dimensions plus {VALUE_COLUMN}). "
            f"Header found: {list(df.columns)}"
        )

    df.columns = [d.label.strip() for d in matrix.dimensions] + [VALUE_COLUMN]

    if df.empty:
        # a response with no rows is legitimate: the combination has no data.
        # An empty column has no dtype to read, so we set it ourselves rather
        # than confusing emptiness with a slipped column mapping. The dimension
        # columns matter as much as the value: concatenating an empty response
        # with a full one would otherwise drag the text columns back to object,
        # so the same download would come back with different dtypes depending
        # on where the chunking happened to cut.
        df[VALUE_COLUMN] = df[VALUE_COLUMN].astype("float64")
        for col in df.columns[:-1]:
            df[col] = df[col].astype(str)
    elif not pd.api.types.is_numeric_dtype(df[VALUE_COLUMN]):
        raise ValueError(
            f"Column {VALUE_COLUMN} is not numeric (dtype "
            f"{df[VALUE_COLUMN].dtype}). A sign the column mapping slipped."
        )
    return df


def _year_of(label) -> int | None:
    """The year inside a period name: 'Anul 2024' gives 2024."""
    m = _YEAR.search(str(label))
    return int(m.group(1)) if m else None


def standardize(df: pd.DataFrame, matrix) -> pd.DataFrame:
    """Add derived columns without dropping or reordering anything.

    For every territorial dimension it can add <label>_siruta, <label>_nivel,
    <label>_tip and <label>_nume, but it only adds the ones that carry
    something: a county dimension gets just <label>_nivel, because counties
    have no SIRUTA code and no settlement type. For every time dimension it
    adds <label>_an. The prefix is the dimension label, so two territorial
    dimensions never collide (FOM104D).

    SIRUTA is a key, so it is added as a new column; the original name stays
    untouched, prefix and all.
    """
    out = df.copy()
    for dim in matrix.dimensions:
        col = dim.label.strip()
        if col not in out.columns:
            continue

        if dim.role == "teritoriu":
            # str() first: a column can hold NaN or a number if the response
            # was odd, and parse_territory expects text
            parsed = [territory.parse_territory(str(v)) for v in out[col]]
            codes = [t[0] for t in parsed]
            kinds = [t[2] for t in parsed]
            name = [t[3] for t in parsed]
            originals = [str(v).strip() for v in out[col]]

            # only add a derived column when it carries something. A county
            # dimension has no SIRUTA and no settlement type, so adding empty
            # <label>_siruta and <label>_tip columns was noise.
            if any(s is not None for s in codes):
                out[f"{col}_siruta"] = pd.array(codes, dtype="Int64")
            # the level is always worth having
            # nullable string: a missing value is pd.NA, not a float NaN
            out[f"{col}_nivel"] = pd.array(
                [t[1] for t in parsed], dtype="string")
            if any(t is not None for t in kinds):
                out[f"{col}_tip"] = pd.array(kinds, dtype="string")
            if any(n != o for n, o in zip(name, originals)):
                out[f"{col}_nume"] = pd.array(name, dtype="string")

        elif dim.role == "timp":
            out[f"{col}_an"] = pd.array(
                [_year_of(v) for v in out[col]], dtype="Int64")
    return out
