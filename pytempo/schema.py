"""Generating PostgreSQL DDL from an indicator's metadata and the registry.

A PURE text function: it opens no connection and imports no driver. pytempo
does not load anything into a database. It writes the SQL, and the project
downstream runs it. That keeps the dependency list at requests and pandas, and
keeps the loading policy where it belongs, with whoever owns the database.

The model: one table per indicator, one text column per dimension, plus the
numeric value, plus exactly the derived columns that get(tidy=True) produces
for that indicator. The derived set is not guessed twice: it is read from
standardize itself, run over the real option labels, so the DDL cannot drift
away from the DataFrame.
"""
import re
import unicodedata

import pandas as pd

from . import parse, territory

VALUE_COLUMN = parse.VALUE_COLUMN

# Postgres truncates identifiers at 63 bytes. We keep the base shorter so the
# longest derived suffix still fits.
MAX_IDENT = 63
MAX_BASE = 55

_NOT_WORD = re.compile(r"[^0-9a-z]+")

# the SQL type for each derived suffix that standardize can add
_DERIVED_TYPES = {
    "_siruta": "integer",
    "_nivel": "text",
    "_tip": "text",
    "_nume": "text",
    "_an": "smallint",
}


def sql_ident(label: str, taken: set | None = None) -> str:
    """A safe snake_case SQL identifier from a dimension label.

    Diacritics are folded, everything that is not a letter or a digit becomes
    an underscore, and an identifier that would start with a digit gets a
    prefix. When `taken` is given, a numeric suffix keeps the name unique.
    """
    folded = unicodedata.normalize("NFKD", str(label or ""))
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    ident = _NOT_WORD.sub("_", folded.lower()).strip("_")
    if not ident:
        ident = "col"
    if ident[0].isdigit():
        ident = f"c_{ident}"
    ident = ident[:MAX_BASE]

    if taken is None:
        return ident
    unique = ident
    n = 2
    while unique in taken:
        suffix = f"_{n}"
        unique = f"{ident[:MAX_BASE - len(suffix)]}{suffix}"
        n += 1
    taken.add(unique)
    return unique


def _sample_frame(matrix) -> pd.DataFrame:
    """A frame built from the real option labels, to ask standardize what it adds.

    Every option of every dimension appears, so a SIRUTA prefix or a settlement
    type present anywhere in the nomenclator is seen.
    """
    if not matrix.dimensions:
        return pd.DataFrame()
    height = max(len(d.options) for d in matrix.dimensions) or 1
    data = {}
    for d in matrix.dimensions:
        labels = [o.label for o in d.options] or [""]
        data[d.label.strip()] = [labels[i % len(labels)] for i in range(height)]
    data[VALUE_COLUMN] = [0.0] * height
    return pd.DataFrame(data)


def derived_columns(matrix) -> list[str]:
    """The derived column names get(tidy=True) produces for this indicator.

    Read from standardize rather than reimplemented, so the DDL and the
    DataFrame cannot disagree.
    """
    frame = _sample_frame(matrix)
    if frame.empty:
        return []
    tidy = parse.standardize(frame, matrix)
    return [c for c in tidy.columns if c not in frame.columns]


def column_mapping(matrix) -> dict:
    """DataFrame column name to SQL column name, for df.rename(columns=...)."""
    taken: set = set()
    mapping = {}
    bases = {}
    for d in matrix.dimensions:
        label = d.label.strip()
        bases[label] = sql_ident(label, taken)
        mapping[label] = bases[label]
    mapping[VALUE_COLUMN] = sql_ident(VALUE_COLUMN, taken)

    for column in derived_columns(matrix):
        for label, base in bases.items():
            for suffix in _DERIVED_TYPES:
                if column == f"{label}{suffix}":
                    mapping[column] = f"{base}{suffix}"[:MAX_IDENT]
    return mapping


def _first_sentence(text: str) -> str:
    first = re.split(r"\.\s", (text or "").strip(), maxsplit=1)[0].strip()
    return first[:400]


def _quote(text: str) -> str:
    """A SQL string literal, with quotes doubled."""
    return "'" + str(text or "").replace("'", "''").replace("\n", " ") + "'"


def table_ddl(matrix, schema: str = "tempo",
              include_comments: bool = True) -> str:
    """CREATE TABLE for one indicator, plus comments and useful indexes.

    Returns one runnable SQL string. Nothing is executed here.
    """
    matrix._ensure_meta()
    table = f"{schema}.{matrix.code.lower()}"
    mapping = column_mapping(matrix)

    lines = [f"CREATE TABLE IF NOT EXISTS {table} ("]
    body = []
    for d in matrix.dimensions:
        body.append(f"    {mapping[d.label.strip()]} text")
    body.append(f"    {mapping[VALUE_COLUMN]} numeric")

    derived = derived_columns(matrix)
    for column in derived:
        suffix = next((s for s in _DERIVED_TYPES if column.endswith(s)), None)
        if suffix and column in mapping:
            body.append(f"    {mapping[column]} {_DERIVED_TYPES[suffix]}")
    lines.append(",\n".join(body))
    lines.append(");")

    out = ["\n".join(lines)]

    if include_comments:
        out.append(
            f"COMMENT ON TABLE {table} IS "
            f"{_quote(matrix.name + '. ' + _first_sentence(matrix.definition))};")
        units = [d.label.strip().split(":", 1)[-1].strip()
                 for d in matrix.dimensions if d.role == "um"]
        if units:
            out.append(
                f"COMMENT ON COLUMN {table}.{mapping[VALUE_COLUMN]} IS "
                f"{_quote('Measured in ' + ', '.join(units))};")

    for column in derived:
        if column not in mapping:
            continue
        if column.endswith("_siruta"):
            out.append(f"CREATE INDEX IF NOT EXISTS "
                       f"{matrix.code.lower()}_{mapping[column]}_idx "
                       f"ON {table} ({mapping[column]});")
        elif column.endswith("_an"):
            out.append(f"CREATE INDEX IF NOT EXISTS "
                       f"{matrix.code.lower()}_{mapping[column]}_idx "
                       f"ON {table} ({mapping[column]});")

    return "\n\n".join(out) + "\n"


def catalog_ddl(schema: str = "tempo") -> str:
    """DDL for the shared infrastructure tables, from the registry.

    Three tables: indicators and dimensions describe the catalogue, territory
    is the SIRUTA lookup you fill from the data you extract. No hard foreign
    keys point at the per indicator tables, because those may not exist yet.
    """
    out = [f"CREATE SCHEMA IF NOT EXISTS {schema};"]

    out.append(
        f"CREATE TABLE IF NOT EXISTS {schema}.indicators (\n"
        f"    code text PRIMARY KEY,\n"
        f"    name text NOT NULL,\n"
        f"    domain text,\n"
        f"    family text,\n"
        f"    periodicity text,\n"
        f"    last_updated text,\n"
        f"    total_cells bigint,\n"
        f"    has_siruta boolean\n"
        f");")
    out.append(
        f"COMMENT ON TABLE {schema}.indicators IS "
        f"{_quote('One row per TEMPO indicator, from the pytempo registry.')};")

    out.append(
        f"CREATE TABLE IF NOT EXISTS {schema}.dimensions (\n"
        f"    code text NOT NULL REFERENCES {schema}.indicators (code),\n"
        f"    position smallint NOT NULL,\n"
        f"    label text NOT NULL,\n"
        f"    role text,\n"
        f"    n_options integer,\n"
        f"    PRIMARY KEY (code, position)\n"
        f");")
    out.append(
        f"COMMENT ON TABLE {schema}.dimensions IS "
        f"{_quote('The dimensions of each indicator, in dimensionsMap order.')};")

    out.append(
        f"CREATE TABLE IF NOT EXISTS {schema}.territory (\n"
        f"    siruta integer PRIMARY KEY,\n"
        f"    name text NOT NULL,\n"
        f"    kind text,\n"
        f"    county text\n"
        f");")
    out.append(
        f"COMMENT ON TABLE {schema}.territory IS "
        f"{_quote('SIRUTA lookup, filled from the data you extract.')};")
    out.append(
        f"CREATE INDEX IF NOT EXISTS territory_county_idx "
        f"ON {schema}.territory (county);")

    return "\n\n".join(out) + "\n"
