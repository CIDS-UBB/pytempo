"""Offline tests for the PostgreSQL DDL generator. No network, no database."""
import re
import sqlite3

import pytempo as t
from pytempo import catalog, client, endpoints, parse, schema

from .test_smoke import FOM101A, FOM104D, SOM101B, TMP1173

ALL = {"FOM104D": FOM104D, "SOM101B": SOM101B, "FOM101A": FOM101A,
       "TMP1173": TMP1173}


def _api(monkeypatch, meta=ALL):
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Indicator {c}"} for c in meta])

    def fake_get_json(url, **kw):
        for code, data in meta.items():
            if url == endpoints.matrix(code):
                return data
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(client, "get_json", fake_get_json)


# ------------------------------------------------------------- sql_ident

def test_sql_ident_folds_diacritics_and_punctuation():
    assert schema.sql_ident("Judete") == "judete"
    assert schema.sql_ident("Macroregiuni, regiuni de dezvoltare") == \
        "macroregiuni_regiuni_de_dezvoltare"
    assert schema.sql_ident("Județe și localități") == "judete_si_localitati"
    assert schema.sql_ident("UM: Numar persoane") == "um_numar_persoane"


def test_sql_ident_handles_awkward_labels():
    assert schema.sql_ident("") == "col"
    assert schema.sql_ident("   ") == "col"
    assert schema.sql_ident("2020 si mai departe").startswith("c_")
    assert len(schema.sql_ident("x" * 200)) <= schema.MAX_BASE


def test_sql_ident_keeps_names_unique():
    taken = set()
    assert schema.sql_ident("Sexe", taken) == "sexe"
    assert schema.sql_ident("Sexe", taken) == "sexe_2"
    assert schema.sql_ident("sexe!", taken) == "sexe_3"


# ------------------------------------------------------------- table_ddl

def test_table_ddl_with_localities(monkeypatch):
    _api(monkeypatch)
    ddl = t.matrix("FOM104D").schema()

    assert "CREATE TABLE IF NOT EXISTS tempo.fom104d (" in ddl
    assert "localitati_siruta integer" in ddl
    assert "localitati_tip text" in ddl
    assert "ani_an smallint" in ddl
    assert "valoare numeric" in ddl
    # the county dimension carries no SIRUTA and no settlement type
    assert "judete_nivel text" in ddl
    assert "judete_siruta" not in ddl
    assert "judete_tip" not in ddl
    # indexes where they help
    assert "CREATE INDEX IF NOT EXISTS fom104d_localitati_siruta_idx" in ddl
    assert "CREATE INDEX IF NOT EXISTS fom104d_ani_an_idx" in ddl


def test_table_ddl_without_siruta(monkeypatch):
    """SOM101B has no locality dimension, so no SIRUTA column is generated."""
    _api(monkeypatch)
    ddl = t.matrix("SOM101B").schema()
    assert "_siruta" not in ddl
    assert "_tip" not in ddl
    assert "_nivel text" in ddl
    assert "_siruta_idx" not in ddl


def test_table_ddl_matches_what_standardize_produces(monkeypatch):
    """The DDL columns and the tidy DataFrame columns must not drift apart."""
    _api(monkeypatch)
    m = t.matrix("FOM104D")
    mapping = schema.column_mapping(m)
    ddl = m.schema()
    for sql_name in mapping.values():
        assert re.search(rf"^    {sql_name} ", ddl, re.MULTILINE), sql_name


def test_table_ddl_comments_can_be_switched_off(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("FOM104D")
    assert "COMMENT ON TABLE" in m.schema()
    assert "COMMENT ON" not in m.schema(include_comments=False)


def test_table_ddl_respects_the_schema_name(monkeypatch):
    _api(monkeypatch)
    ddl = t.matrix("FOM104D").schema(schema="statistica")
    assert "statistica.fom104d" in ddl
    assert "tempo.fom104d" not in ddl


# --------------------------------------------------------- column_mapping

def test_column_mapping_covers_every_column(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("FOM104D")
    mapping = schema.column_mapping(m)

    assert mapping["Judete"] == "judete"
    assert mapping["Localitati"] == "localitati"
    assert mapping["Valoare"] == "valoare"
    assert mapping["Localitati_siruta"] == "localitati_siruta"
    assert mapping["Ani_an"] == "ani_an"
    # every derived column standardize adds has a SQL name
    for column in schema.derived_columns(m):
        assert column in mapping, column


# ------------------------------------------------------------ catalog_ddl

def test_catalog_ddl_has_the_three_tables():
    ddl = t.schema_catalog()
    for table in ("tempo.indicators", "tempo.dimensions", "tempo.territory"):
        assert f"CREATE TABLE IF NOT EXISTS {table} (" in ddl
    assert "siruta integer PRIMARY KEY" in ddl
    assert "REFERENCES tempo.indicators (code)" in ddl
    assert "COMMENT ON TABLE tempo.territory" in ddl


def test_catalog_ddl_respects_the_schema_name():
    ddl = t.schema_catalog(schema="statistica")
    assert "CREATE SCHEMA IF NOT EXISTS statistica;" in ddl
    assert "statistica.indicators" in ddl


# ----------------------------------------------------------- shape of SQL

def _statements(ddl: str) -> list[str]:
    return [s.strip() for s in ddl.split(";") if s.strip()]


def test_generated_sql_is_well_formed(monkeypatch):
    _api(monkeypatch)
    for ddl in (t.matrix("FOM104D").schema(), t.matrix("SOM101B").schema(),
                t.schema_catalog()):
        assert ddl.rstrip().endswith(";")
        for stmt in _statements(ddl):
            assert stmt.count("(") == stmt.count(")"), stmt[:60]
        # quotes come in pairs once doubled ones are removed
        assert ddl.replace("''", "").count("'") % 2 == 0


def test_create_table_parses_in_sqlite(monkeypatch):
    """A smoke test on the structure, using the stdlib parser.

    sqlite is not Postgres, so only the CREATE TABLE statements are tried, with
    the schema prefix removed. It catches a broken column list or a stray comma.
    """
    _api(monkeypatch)
    con = sqlite3.connect(":memory:")
    for ddl in (t.matrix("FOM104D").schema(include_comments=False),
                t.matrix("TMP1173").schema(include_comments=False)):
        for stmt in _statements(ddl):
            if not stmt.upper().startswith("CREATE TABLE"):
                continue
            con.execute(stmt.replace("tempo.", ""))
    names = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"fom104d", "tmp1173"} <= names
    con.close()


def test_catalog_ddl_parses_in_sqlite():
    con = sqlite3.connect(":memory:")
    for stmt in _statements(t.schema_catalog()):
        if stmt.upper().startswith("CREATE TABLE"):
            con.execute(stmt.replace("tempo.", ""))
    names = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"indicators", "dimensions", "territory"} <= names
    con.close()


def test_derived_columns_are_read_from_standardize(monkeypatch):
    """The generator asks standardize rather than reimplementing its rules."""
    _api(monkeypatch)
    m = t.matrix("TMP1173")
    # monitoring stations: no SIRUTA, no settlement type, only a level
    assert schema.derived_columns(m) == [
        "Statii de monitorizare de tip fond urban - Localitate_nivel",
        "Ani_an"]
    assert "_siruta" not in t.matrix("TMP1173").schema()
