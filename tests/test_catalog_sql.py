"""Offline tests for the SQL contract: sql_ident, the catalogue tables and their
rows, sql_columns(), and the latest period. No network, no database.
"""
import json
import re
import sqlite3
from pathlib import Path

import pytempo as t
from pytempo import catalog, client, endpoints, parse, schema

from .test_smoke import FOM101A, FOM104D, TMP1173

FIXTURES = Path(__file__).parent / "fixtures"
META = {cod: json.loads((FIXTURES / f"{cod}_meta.json").read_text(
    encoding="utf-8")) for cod in ("GOS102A", "LOC108B", "FOM121A")}
META.update({"FOM101A": FOM101A, "FOM104D": FOM104D, "TMP1173": TMP1173})


def _api(monkeypatch):
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Indicator {c}"} for c in META])

    def fake_get_json(url, **kw):
        for code, data in META.items():
            if url == endpoints.matrix(code):
                return data
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(client, "get_json", fake_get_json)


def _columns(ddl, table):
    block = re.search(
        rf"CREATE TABLE IF NOT EXISTS tempo\.{table} \((.*?)\n\);",
        ddl, re.S).group(1)
    return [line.strip().split()[0] for line in block.strip().split("\n")
            if not line.strip().startswith("PRIMARY")]


def _create(con, ddl):
    for stmt in ddl.split(";"):
        stmt = stmt.strip()
        if stmt.upper().startswith("CREATE TABLE"):
            con.execute(stmt.replace("tempo.", ""))


# ------------------------------------- sql_ident as a public contract

# the names every database built from pytempo carries: changing any of these
# is a breaking change, an existing table would meet other column names
SQL_IDENT_CONTRACT = {
    "CAEN Rev.2  (activitati ale economiei nationale)":
        "caen_rev_2_activitati_ale_economiei_nationale",
    "Macroregiuni  regiuni de dezvoltare si judete":
        "macroregiuni_regiuni_de_dezvoltare_si_judete",
    "Județe și localități": "judete_si_localitati",
    "Unități de măsură": "unitati_de_masura",
    "UM: Milioane lei, lei RON, mii lei RON,milioane lei RON (incepand cu 2005)":
        "um_milioane_lei_lei_ron_mii_lei_ron_milioane_lei_ron_in",
    "ANI/UM": "ani_um",
    "CAEN Rev.1 - grupe": "caen_rev_1_grupe",
    "2020 si mai departe": "c_2020_si_mai_departe",
    "Valoare": "valoare",
    "Valoare_confidential": "valoare_confidential",
}

LONG = ("Numarul salariatilor cu program complet de lucru care au fost "
        "platiti intreaga luna")


def test_sql_ident_contract_on_hard_labels():
    for label, expected in SQL_IDENT_CONTRACT.items():
        assert schema.sql_ident(label) == expected, label


def test_sql_ident_truncates_long_labels_to_the_base_length():
    assert schema.sql_ident(LONG) == \
        "numarul_salariatilor_cu_program_complet_de_lucru_care_a"
    assert len(schema.sql_ident(LONG)) == schema.MAX_BASE


def test_sql_ident_forced_collision_gets_a_numbered_suffix():
    taken = set()
    assert [schema.sql_ident(x, taken) for x in ("Sexe", "sexe", "SEXE!")] \
        == ["sexe", "sexe_2", "sexe_3"]
    taken = set()
    first, second = schema.sql_ident(LONG, taken), schema.sql_ident(LONG, taken)
    assert second == "numarul_salariatilor_cu_program_complet_de_lucru_care_2"
    assert len(first) == len(second) == schema.MAX_BASE


# ------------------------------------- the catalogue tables and their rows

def test_catalog_ddl_has_no_family_and_carries_the_prose():
    ddl = t.schema_catalog()
    indicators = _columns(ddl, "indicators")
    assert "family" not in indicators
    for column in ("total_cells", "definition", "methodology", "sources",
                   "observations", "latest_period", "latest_period_label"):
        assert column in indicators
    assert "registry" not in ddl
    dimensions = _columns(ddl, "dimensions")
    assert dimensions[dimensions.index("label") + 1] == "sql_name"
    assert "level" in dimensions


def test_catalog_rows_are_keyed_like_the_ddl(monkeypatch):
    _api(monkeypatch)
    ddl = t.schema_catalog()
    for code in META:
        rows = t.matrix(code).catalog_rows()
        assert list(rows["indicator"]) == _columns(ddl, "indicators")
        for row in rows["dimensions"]:
            assert list(row) == _columns(ddl, "dimensions")


def test_catalog_rows_insert_into_the_catalog_tables(monkeypatch):
    _api(monkeypatch)
    con = sqlite3.connect(":memory:")
    _create(con, t.schema_catalog())
    for code in ("GOS102A", "LOC108B", "FOM121A"):
        rows = t.matrix(code).catalog_rows()
        ind = rows["indicator"]
        con.execute(f"INSERT INTO indicators ({', '.join(ind)}) VALUES "
                    f"({', '.join('?' * len(ind))})", list(ind.values()))
        for row in rows["dimensions"]:
            con.execute(f"INSERT INTO dimensions ({', '.join(row)}) VALUES "
                        f"({', '.join('?' * len(row))})", list(row.values()))
    assert con.execute("SELECT count(*) FROM indicators").fetchone()[0] == 3
    level = con.execute("SELECT level FROM dimensions WHERE code = 'GOS102A' "
                        "AND label = 'Municipii si orase'").fetchone()[0]
    assert level == "localitate"
    con.close()


def test_catalog_rows_take_everything_from_the_metadata(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("GOS102A")
    rows = m.catalog_rows()
    ind = rows["indicator"]
    assert ind["code"] == "GOS102A" and ind["name"] == m.name
    assert ind["definition"] == (m.definition or None)
    cells = 1
    for d in m.dimensions:
        cells *= len(d.options)
    assert ind["total_cells"] == cells
    by_label = {d["label"]: d for d in rows["dimensions"]}
    assert by_label["Municipii si orase"]["sql_name"] == "municipii_si_orase"
    assert by_label["Municipii si orase"]["level"] == "localitate"
    assert by_label["Ani"]["level"] is None
    assert [d["position"] for d in rows["dimensions"]] == list(
        range(len(m.dimensions)))


def test_catalog_rows_sql_names_match_the_table(monkeypatch):
    """The dimensions table names each column the way the indicator table
    does, so a query can join the two."""
    _api(monkeypatch)
    for code in ("GOS102A", "LOC108B", "FOM121A"):
        m = t.matrix(code)
        mapping = t.column_mapping(m)
        for row in m.catalog_rows()["dimensions"]:
            assert row["sql_name"] == mapping[row["label"]]


# --------------------------------------------- sql_columns, by meaning

def test_sql_columns_finds_the_localities_whatever_their_name(monkeypatch):
    _api(monkeypatch)
    cols = t.matrix("GOS102A").sql_columns()
    assert list(cols) == list(schema.SQL_COLUMN_ROLES)
    assert cols["siruta"] == "municipii_si_orase_siruta"
    assert cols["name"] == "municipii_si_orase_nume"
    assert cols["level"] == "municipii_si_orase_nivel"
    assert cols["year"] == "ani_an" and cols["period"] == "ani"
    assert cols["value"] == "valoare"
    assert cols["confidential"] == "valoare_confidential"


def test_sql_columns_says_when_the_unit_selects_measures(monkeypatch):
    _api(monkeypatch)
    loc108b = t.matrix("LOC108B").sql_columns()
    assert loc108b["unit"] == "um_numar_mp_suprafata_utila"
    assert loc108b["unit_options"] == 2
    fom121a = t.matrix("FOM121A").sql_columns()
    assert fom121a["unit"] == "unitati_de_masura"
    assert fom121a["unit_options"] == 2
    assert t.matrix("GOS102A").sql_columns()["unit_options"] == 1


def test_sql_columns_absent_roles_are_none_never_missing(monkeypatch):
    _api(monkeypatch)
    cols = t.matrix("FOM121A").sql_columns()
    assert list(cols) == list(schema.SQL_COLUMN_ROLES)
    assert cols["territory"] is None and cols["siruta"] is None
    county = t.matrix("FOM101A").sql_columns()
    assert county["siruta"] is None
    assert county["name"] == county["territory"]


def test_sql_columns_names_exist_in_the_table(monkeypatch):
    _api(monkeypatch)
    for code in ("GOS102A", "LOC108B", "FOM121A", "FOM104D"):
        m = t.matrix(code)
        ddl = m.schema(include_comments=False)
        for role, name in m.sql_columns().items():
            if name is not None and role != "unit_options":
                assert re.search(rf"\b{name}\b", ddl), (code, role, name)


# ------------------------------------------------- the latest period

def test_period_forms_are_normalized():
    assert parse.period_of("Anul 2024") == ("2024", (2024, 12, 1))
    assert parse.period_of("Trimestrul I 2024") == ("2024-Q1", (2024, 3, 2))
    assert parse.period_of("Trimestrul IV 2024")[0] == "2024-Q4"
    assert parse.period_of("Luna mai 2026") == ("2026-05", (2026, 5, 3))
    assert parse.period_of("Luna Decembrie 2025")[0] == "2025-12"
    assert parse.period_of("Anii 1901 - 2000") == ("1901-2000", (2000, 12, 0))
    assert parse.period_of("Semestrul I 2024") is None


def test_latest_period_is_the_one_that_ends_last_not_the_last_option():
    """PPA102C lists its months before its quarters."""
    labels = ["Luna aprilie 2026", "Luna mai 2026", "Trimestrul I 2026"]
    assert parse.latest_period(labels) == ("2026-05", "Luna mai 2026")


def test_at_the_same_end_the_finer_period_wins():
    labels = ["Anul 2025", "Trimestrul IV 2025", "Luna decembrie 2025"]
    assert parse.latest_period(labels) == ("2025-12", "Luna decembrie 2025")
    assert parse.latest_period(["Anul 2025", "Trimestrul IV 2025"]) == \
        ("2025-Q4", "Trimestrul IV 2025")


def test_an_unknown_label_is_left_out_not_guessed():
    assert parse.latest_period(["Anul 2020", "Semestrul II 2024"]) == \
        ("2020", "Anul 2020")
    assert parse.latest_period(["Semestrul II 2024"]) == (None, None)
    assert parse.latest_period([]) == (None, None)


def test_normalized_periods_sort_as_text_only_within_one_granularity():
    """Why catalog_ddl says to compare across granularities by end."""
    assert sorted(["2024-Q3", "2024-Q1", "2023-Q4"]) == \
        ["2023-Q4", "2024-Q1", "2024-Q3"]
    assert sorted(["2026-05", "2025-12", "2026-01"]) == \
        ["2025-12", "2026-01", "2026-05"]
    # across granularities text order is not time order: the year ends last
    assert sorted(["2024", "2024-Q1", "2024-05"]) == \
        ["2024", "2024-05", "2024-Q1"]


# ---------------------------- the data table and the frame get() returns

def _answers_with_every_option(m):
    """pivot answering with every option of every dimension, as INS would."""
    frame = schema._sample_frame(m)
    # INS strips commas out of labels, in the header as in the values
    header = ", ".join(d.label.replace(",", " ") for d in m.dimensions) \
        + ", Valoare"
    lines = [", ".join(str(v).replace(",", " ") for v in row) + ", 1.0"
             for row in frame.drop(columns=["Valoare"]).itertuples(index=False)]
    text = header + "\n" + "\n".join(lines) + "\n"
    return lambda payload, **kw: text


def test_table_ddl_and_the_renamed_frame_have_the_same_columns(monkeypatch):
    """Two pieces of code that have to agree: the CREATE TABLE and the frame
    renamed by column_mapping. If they drift, the first insert fails."""
    _api(monkeypatch)
    for code in ("GOS102A", "LOC108B", "FOM121A", "FOM104D", "FOM101A"):
        m = t.matrix(code)
        monkeypatch.setattr(client, "post_pivot", _answers_with_every_option(m))
        df = m.get(level=None, progress=False, confirm=False)
        renamed = df.rename(columns=t.column_mapping(m))
        ddl = m.schema(include_comments=False)
        assert list(renamed.columns) == _columns(ddl, code.lower()), code

        con = sqlite3.connect(":memory:")
        _create(con, ddl)
        sample = renamed.head(3).astype(object).where(renamed.head(3).notna(),
                                                      None)
        con.executemany(
            f"INSERT INTO {code.lower()} ({', '.join(sample.columns)}) VALUES "
            f"({', '.join('?' * len(sample.columns))})",
            [tuple(row) for row in sample.itertuples(index=False)])
        assert con.execute(f"SELECT count(*) FROM {code.lower()}").fetchone()[0] == 3
        con.close()
