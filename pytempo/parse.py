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

The value column is not always a number. INS writes 'c' for a confidential cell:
the figure exists, but publishing it would identify a reporting unit. That is
neither ':' (no figure, which arrives as no row) nor '0' (a measured zero). It
arrives as a row whose Valoare is NaN and whose Valoare_confidential is True.
"""
import io
import re

import pandas as pd

from . import territory

VALUE_COLUMN = "Valoare"

# True on the rows INS suppressed for confidentiality. Present on every frame
# pivot_csv_to_dataframe returns, False throughout when nothing was suppressed:
# a column that appeared only in slices with a 'c' would make the same download
# come back with different columns depending on where the chunking cut.
CONFIDENTIAL_COLUMN = f"{VALUE_COLUMN}_confidential"

# what INS writes in the value column instead of a number, and what it means.
# The single place the package knows these: the parser cleans them out, and the
# registry validation uses the same list to tell a known marker from a stray
# string. The TEMPO legend lists ':' for missing and 'c' for confidential; ':'
# never reaches the CSV, the row is left out instead. Checked against live
# responses in October 2026: a stratified sample of 144 indicators from the
# registry, 35 of them at locality level, 1,021,501 rows, plus 28 CAEN
# indicators before that. 'c' is the only textual value that appeared. The
# matrix metadata never define it; the meaning rests on the TEMPO legend. Any
# other string is unknown and still stops the parse, as it should.
CONFIDENTIAL_MARKERS = frozenset({"c"})

_YEAR = re.compile(r"\b(\d{4})\b")


def unknown_markers(values) -> list[str]:
    """The values that are neither a number nor a marker INS is known to use.

    Empty means the column is clean once the markers are taken out. Anything
    left is not INS speaking but the column mapping slipping.
    """
    found = set()
    for v in values:
        if pd.isna(v):
            continue
        text = str(v).strip()
        if text in CONFIDENTIAL_MARKERS:
            continue
        try:
            float(text)
        except ValueError:
            found.add(text)
    return sorted(found)


def _confidential_out(df: pd.DataFrame) -> pd.DataFrame:
    """Valoare as float64 and the confidentiality flag beside it.

    A 'c' becomes NaN, so any calculation runs, and the flag keeps the fact
    that a figure exists there. Valoare is cast to float64 whatever came in,
    for the same reason the flag always exists: a slice of whole numbers would
    otherwise be int64 and its neighbour with a 'c' float64.
    """
    values = df[VALUE_COLUMN]
    flag = pd.Series(False, index=df.index, dtype=bool)
    if not pd.api.types.is_numeric_dtype(values):
        text = values.astype("string").str.strip()
        flag = text.isin(CONFIDENTIAL_MARKERS).fillna(False).astype(bool)
        if not unknown_markers(values[~flag]):
            values = pd.to_numeric(text.mask(flag), errors="raise")
    if not pd.api.types.is_numeric_dtype(values):
        # what is left once the markers are out is not INS speaking
        raise ValueError(
            f"Column {VALUE_COLUMN} is not numeric (dtype {values.dtype}), "
            f"values such as {unknown_markers(values)[:3]}. A sign the column "
            f"mapping slipped.")
    df[VALUE_COLUMN] = values.astype("float64")
    df[CONFIDENTIAL_COLUMN] = flag.to_numpy(dtype=bool)
    return df


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
        df[CONFIDENTIAL_COLUMN] = pd.Series(dtype=bool)
        return df
    # the dtype guard runs inside, after the markers are out, so it still
    # catches a slipped mapping and nothing else
    return _confidential_out(df)


_MONTHS = {name: number for number, name in enumerate(
    ("ianuarie februarie martie aprilie mai iunie iulie august septembrie "
     "octombrie noiembrie decembrie").split(), 1)}
_QUARTERS = {"I": 1, "II": 2, "III": 3, "IV": 4}
_PERIOD_FORMS = (
    (re.compile(r"Anul (\d{4})"), "year"),
    (re.compile(r"Trimestrul (IV|III|II|I) (\d{4})"), "quarter"),
    (re.compile(r"Luna (\w+) (\d{4})", re.IGNORECASE), "month"),
    (re.compile(r"Anii (\d{4}) ?- ?(\d{4})"), "years"),
)
# at the same end, the finer period says more: a month over its quarter over
# its year
_FINENESS = {"years": 0, "year": 1, "quarter": 2, "month": 3}


def period_of(label) -> tuple | None:
    """A TEMPO period label, normalized, with the month it ends in.

    Returns (normalized, (end_year, end_month, fineness)), or None for a label
    of none of the four forms measured across the catalogue:

        'Anul 2024'           '2024'        ends December 2024
        'Trimestrul I 2024'   '2024-Q1'     ends March 2024
        'Luna mai 2026'       '2026-05'     ends May 2026
        'Anii 1901 - 2000'    '1901-2000'   ends December 2000

    The last is a single case, ZDP1321, a climate baseline averaged over the
    century; it is kept as the range it is rather than forced into a year.
    """
    text = str(label or "").strip()
    for pattern, kind in _PERIOD_FORMS:
        m = pattern.fullmatch(text)
        if not m:
            continue
        if kind == "year":
            year = int(m.group(1))
            return str(year), (year, 12, _FINENESS[kind])
        if kind == "quarter":
            year, quarter = int(m.group(2)), _QUARTERS[m.group(1)]
            return f"{year}-Q{quarter}", (year, 3 * quarter, _FINENESS[kind])
        if kind == "month":
            month = _MONTHS.get(m.group(1).lower())
            if month is None:
                return None
            year = int(m.group(2))
            return f"{year}-{month:02d}", (year, month, _FINENESS[kind])
        first, last = int(m.group(1)), int(m.group(2))
        return f"{first}-{last}", (last, 12, _FINENESS[kind])
    return None


def latest_period(labels) -> tuple:
    """The period that ends last, as (normalized, INS label), or (None, None).

    Not the last option: INS lists PPA102C's months before its quarters, so
    the last option is 'Trimestrul I 2026' while 'Luna mai 2026' exists, and
    132 time dimensions mix years with quarters or months. At the same end the
    finer period wins: 'Luna decembrie 2025' over 'Trimestrul IV 2025' over
    'Anul 2025'. A label of no known form is left out rather than guessed.
    """
    best = None
    for label in labels:
        parsed = period_of(label)
        if parsed is not None and (best is None or parsed[1] > best[0][1]):
            best = (parsed, str(label).strip())
    if best is None:
        return None, None
    return best[0][0], best[1]


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
    return _locality_total_takes_the_county_level(out, matrix)


def _locality_total_takes_the_county_level(out: pd.DataFrame,
                                           matrix) -> pd.DataFrame:
    """With county and locality as two dimensions, a locality TOTAL is the
    total of the county on the same row, so it is at that county's level.

    Read on its own, the label TOTAL says national, and (Alba, TOTAL), the
    county row get(level=None) and get(level='judet') bring back, would carry
    'judet' in one level column and 'national' in the other. Taking the
    county's level makes the locality <label>_nivel name the level of the whole
    row, national, judet or localitate, so the levels of a mixed frame separate
    on that one column.
    """
    territorial = [d for d in matrix.dimensions
                   if d.role == "teritoriu" and d.label.strip() in out.columns]
    localities = [d for d in territorial
                  if territory.is_locality_dimension(d, matrix.details)]
    if len(localities) != 1 or len(territorial) < 2:
        return out
    loc = localities[0].label.strip()
    county = next(d.label.strip() for d in territorial if d is not localities[0])
    is_total = out[loc].map(lambda v: territory.is_total_label(str(v)))
    if is_total.any():
        level = out[f"{loc}_nivel"].copy()
        level[is_total] = out.loc[is_total, f"{county}_nivel"]
        out[f"{loc}_nivel"] = level
    return out
