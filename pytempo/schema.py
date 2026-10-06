"""Generating PostgreSQL DDL from an indicator's metadata and the registry.

A PURE text function: it opens no connection and imports no driver. pytempo
does not load anything into a database. It writes the SQL, and the project
downstream runs it. That keeps the dependency list at requests and pandas, and
keeps the loading policy where it belongs, with whoever owns the database.

The model: one table per indicator, one text column per dimension, plus the
numeric value and its confidentiality flag, plus exactly the derived columns
that get(tidy=True) produces for that indicator. The derived set is not guessed
twice: it is read from standardize itself, run over the real option labels, so
the DDL cannot drift away from the DataFrame.
"""
import re
import unicodedata

import pandas as pd

from . import parse, territory

VALUE_COLUMN = parse.VALUE_COLUMN
CONFIDENTIAL_COLUMN = parse.CONFIDENTIAL_COLUMN

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

    The normalization is a public contract: the column names of every database
    built from pytempo come out of it, so changing it is a breaking change,
    and an existing table would meet differently named columns.
    tests/test_catalog_sql.py pins it on the hard cases. Across the whole
    catalogue, 1927 indicators, no two dimensions of one indicator fold to the
    same name, nor to the value columns, so the suffix is never needed on real
    data. Were it needed, order would decide: column_mapping() goes through
    the dimensions in dimensionsMap order, so the later of two colliding
    labels gets '_2'.
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
    mapping[CONFIDENTIAL_COLUMN] = sql_ident(CONFIDENTIAL_COLUMN, taken)

    for column in derived_columns(matrix):
        for label, base in bases.items():
            for suffix in _DERIVED_TYPES:
                if column == f"{label}{suffix}":
                    mapping[column] = f"{base}{suffix}"[:MAX_IDENT]
    return mapping


# what sql_columns() answers, always all of them, in this order
SQL_COLUMN_ROLES = ("value", "confidential", "period", "year", "territory",
                    "siruta", "level", "name", "unit", "unit_options")


def sql_columns(matrix) -> dict:
    """Which SQL column holds what, by meaning rather than by name.

    column_mapping() says how every column is renamed; this says where the
    value is, where the year is, where SIRUTA is, without knowing that GOS102A
    calls its localities 'Municipii si orase'. Every key in SQL_COLUMN_ROLES is
    always there, None when the indicator has no such column, so the same code
    works on every indicator and a missing role is a None to test, not a
    KeyError.

        value          the numeric value
        confidential   True where INS suppressed the figure ('c')
        period         the original time column, 'Anul 2024', 'Luna mai 2026'
        year           the year of that period, smallint
        territory      the original column of the finest territory
        siruta         its SIRUTA code, for localities
        level          its territorial level, national ... localitate
        name           its clean name: the derived one where the label carried
                       a SIRUTA prefix, the original column otherwise
        unit           the unit of measure column
        unit_options   how many options that column has

    unit_options above 1 means the unit is a selector of measures, not a
    label: LOC108B has every year twice, once as a count of building permits,
    once as square metres. Summing over it adds the two.
    """
    matrix._ensure_meta()
    mapping = column_mapping(matrix)
    out = dict.fromkeys(SQL_COLUMN_ROLES)
    out["value"] = mapping[VALUE_COLUMN]
    out["confidential"] = mapping[CONFIDENTIAL_COLUMN]

    time = [d for d in matrix.dimensions if d.role == "timp"]
    if time:
        column = time[0].label.strip()
        out["period"] = mapping[column]
        out["year"] = mapping.get(f"{column}_an")

    fine = matrix.territory_columns()
    if fine:
        out["territory"] = mapping.get(fine["label"])
        out["siruta"] = mapping.get(fine.get("siruta"))
        out["level"] = mapping.get(fine.get("nivel"))
        out["name"] = mapping.get(fine.get("nume")) or out["territory"]

    units = [d for d in matrix.dimensions if d.role == "um"]
    if units:
        out["unit"] = mapping[units[0].label.strip()]
        out["unit_options"] = len(units[0].options)
    return out


def catalog_rows(matrix) -> dict:
    """The rows this indicator contributes to the catalogue tables.

    {'indicator': {...}, 'dimensions': [{...}, ...]}, keyed exactly like the
    columns catalog_ddl() declares, ready to insert. One call for both tables:
    they are filled at the same moment, from the same metadata, by the same
    caller, and two calls could drift apart.

    Everything comes from the indicator's own metadata, so the rows are filled
    as each indicator is loaded rather than all at once from a catalogue: the
    definitions, methodologies and observations are only in the live metadata,
    and the prose stays whole, the way INS wrote it.
    """
    from .matrix import _clean  # local: matrix imports this module lazily

    matrix._ensure_meta()
    mapping = column_mapping(matrix)
    time = [d for d in matrix.dimensions if d.role == "timp"]
    latest, latest_label = (parse.latest_period(o.label for o in time[0].options)
                            if time else (None, None))
    total_cells = 1
    for d in matrix.dimensions:
        total_cells *= len(d.options)
    sources = [" ".join(p for p in (s.get("nume"), f"({s['tip']})"
                                    if s.get("tip") else None) if p)
               for s in (matrix.sources or []) if isinstance(s, dict)]

    indicator = {
        "code": matrix.code,
        "name": matrix.name,
        "domain": (_clean(matrix.ancestors[0].get("name", ""))
                   if matrix.ancestors else None),
        "periodicity": ", ".join(matrix.periodicity or []) or None,
        "last_updated": matrix.last_updated or None,
        "total_cells": total_cells if matrix.dimensions else 0,
        "has_siruta": matrix.has_siruta,
        "definition": matrix.definition or None,
        "methodology": matrix.methodology or None,
        "sources": "; ".join(sources) or None,
        "observations": matrix.observations or None,
        "latest_period": latest,
        "latest_period_label": latest_label,
    }
    dimensions = [{
        "code": matrix.code,
        "position": d.dim_index,
        "label": d.label.strip(),
        "sql_name": mapping[d.label.strip()],
        "role": d.role,
        "level": d.finest_level or None,
        "n_options": len(d.options),
    } for d in matrix.dimensions]
    return {"indicator": indicator, "dimensions": dimensions}


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
    body.append(f"    {mapping[CONFIDENTIAL_COLUMN]} boolean")

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
        units = [territory.unit_text(d)
                 for d in matrix.dimensions if d.role == "um"]
        if units:
            out.append(
                f"COMMENT ON COLUMN {table}.{mapping[VALUE_COLUMN]} IS "
                f"{_quote('Measured in ' + ', '.join(units))};")
        out.append(
            f"COMMENT ON COLUMN {table}.{mapping[CONFIDENTIAL_COLUMN]} IS "
            f"{_quote('True where INS suppressed the figure as confidential (c): it exists but is not published, so the value is NULL')};")

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
    """DDL for the shared infrastructure tables.

    Three tables: indicators and dimensions describe the catalogue, territory
    is the SIRUTA lookup you fill from the data you extract. No hard foreign
    keys point at the per indicator tables, because those may not exist yet.
    The rows for the first two come from m.catalog_rows(), one indicator at a
    time, keyed like these columns; nothing here reads the internal registry.

    latest_period is normalized, '2024', '2024-Q1', '2026-05', and sorts
    lexicographically only within one granularity: '2024' < '2024-05' <
    '2024-Q1' as text, though the year ends last. Compare periods of different
    granularity by when they end, not as strings. latest_period_label keeps the
    INS label it came from, the one thing to rebuild it from if a form is ever
    read wrong.
    """
    out = [f"CREATE SCHEMA IF NOT EXISTS {schema};"]

    out.append(
        f"CREATE TABLE IF NOT EXISTS {schema}.indicators (\n"
        f"    code text PRIMARY KEY,\n"
        f"    name text NOT NULL,\n"
        f"    domain text,\n"
        f"    periodicity text,\n"
        f"    last_updated text,\n"
        f"    total_cells bigint,\n"
        f"    has_siruta boolean,\n"
        f"    definition text,\n"
        f"    methodology text,\n"
        f"    sources text,\n"
        f"    observations text,\n"
        f"    latest_period text,\n"
        f"    latest_period_label text\n"
        f");")
    out.append(
        f"COMMENT ON TABLE {schema}.indicators IS "
        f"{_quote('One row per TEMPO indicator, from its own metadata: m.catalog_rows().')};")
    out.append(
        f"COMMENT ON COLUMN {schema}.indicators.latest_period IS "
        f"{_quote('The period that ends last, normalized: 2024, 2024-Q1, 2026-05. Sorts as text only within one granularity.')};")

    out.append(
        f"CREATE TABLE IF NOT EXISTS {schema}.dimensions (\n"
        f"    code text NOT NULL REFERENCES {schema}.indicators (code),\n"
        f"    position smallint NOT NULL,\n"
        f"    label text NOT NULL,\n"
        f"    sql_name text NOT NULL,\n"
        f"    role text,\n"
        f"    level text,\n"
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
