"""Offline tests for the df.tempo accessor. No network, hand built frames."""
import pandas as pd
import pytest

import pytempo as t  # noqa: F401  importing registers the accessor

TERR = "Macroregiuni, regiuni de dezvoltare si judete"


def tidy_frame(rows=None, levels=None):
    """A frame shaped like get(tidy=True) on FOM101A."""
    rows = rows or [
        ("Total", "Cluj", "Anul 2020", 2020, 300.0),
        ("Total", "Cluj", "Anul 2021", 2021, 310.0),
        ("Total", "Cluj", "Anul 2022", 2022, 305.0),
        ("Total", "Alba", "Anul 2020", 2020, 100.0),
        ("Total", "Alba", "Anul 2021", 2021, 110.0),
        ("Total", "Alba", "Anul 2022", 2022, 120.0),
    ]
    frame = pd.DataFrame(rows, columns=["Sexe", TERR, "Ani", "Ani_an",
                                        "Valoare"])
    frame["UM: Mii persoane"] = "Mii persoane"
    frame[f"{TERR}_nivel"] = levels if levels else "judet"
    return frame[["Sexe", TERR, "Ani", "UM: Mii persoane", "Valoare",
                  f"{TERR}_nivel", "Ani_an"]]


# ------------------------------------------------------------------ guard

def test_accessor_rejects_a_foreign_frame():
    stranger = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    for call in (lambda: stranger.tempo.wide(),
                 lambda: stranger.tempo.coverage()):
        with pytest.raises(ValueError) as info:
            call()
        assert "does not look like pytempo tidy output" in str(info.value)
        assert "m.get()" in str(info.value)


def test_accessor_accepts_a_tidy_frame():
    assert tidy_frame().tempo._is_tidy is True


# ------------------------------------------------------------------- wide

def test_wide_puts_years_in_columns():
    wide = tidy_frame().tempo.wide()
    assert 2020 in wide.columns and 2022 in wide.columns
    # one row per county and sex, not one per year
    assert len(wide) == 2
    assert set(wide[TERR]) == {"Alba", "Cluj"}
    cluj = wide[wide[TERR] == "Cluj"].iloc[0]
    assert cluj[2021] == 310.0


def test_wide_drops_the_original_time_and_unit_columns():
    wide = tidy_frame().tempo.wide()
    assert "Ani" not in wide.columns          # redundant with Ani_an
    assert "Ani_an" not in wide.columns
    assert "UM: Mii persoane" not in wide.columns
    assert f"{TERR}_nivel" not in wide.columns
    assert "Valoare" not in wide.columns
    # the real dimensions stay
    assert "Sexe" in wide.columns and TERR in wide.columns


def test_wide_keeps_a_unit_column_that_actually_varies():
    """A unit column is only dropped when it never changes."""
    frame = tidy_frame()
    frame.loc[frame.index[:3], "UM: Mii persoane"] = "Persoane"
    wide = frame.tempo.wide()
    assert "UM: Mii persoane" in wide.columns


def test_wide_does_not_touch_the_original():
    frame = tidy_frame()
    before = frame.copy()
    frame.tempo.wide()
    pd.testing.assert_frame_equal(frame, before)


def test_wide_without_a_year_column():
    frame = tidy_frame().drop(columns=["Ani_an"])
    with pytest.raises(ValueError) as info:
        frame.tempo.wide()
    assert "no year column" in str(info.value)


def test_wide_rejects_an_unknown_value_column():
    with pytest.raises(ValueError) as info:
        tidy_frame().tempo.wide(values="Nope")
    assert "Nope" in str(info.value)


# --------------------------------------------------------------- coverage

def test_coverage_counts_years_and_holes():
    rows = [
        ("Total", "Cluj", "Anul 2020", 2020, 300.0),
        ("Total", "Cluj", "Anul 2022", 2022, 305.0),     # 2021 missing
        ("Total", "Alba", "Anul 2020", 2020, 100.0),
        ("Total", "Alba", "Anul 2021", 2021, 110.0),
        ("Total", "Alba", "Anul 2022", 2022, 120.0),
    ]
    report = tidy_frame(rows).tempo.coverage().set_index(TERR)

    assert report.loc["Alba", "n_years"] == 3
    assert report.loc["Alba", "missing_years"] == 0
    assert report.loc["Cluj", "n_years"] == 2
    assert report.loc["Cluj", "missing_years"] == 1      # 2021
    assert report.loc["Cluj", "first_year"] == 2020
    assert report.loc["Cluj", "last_year"] == 2022


def test_coverage_reports_extremes_with_their_year():
    report = tidy_frame().tempo.coverage().set_index(TERR)
    assert report.loc["Alba", "min_value"] == 100.0
    assert report.loc["Alba", "min_year"] == 2020
    assert report.loc["Alba", "max_value"] == 120.0
    assert report.loc["Alba", "max_year"] == 2022


def test_coverage_shows_the_level_when_they_are_mixed():
    frame = tidy_frame(levels=["judet"] * 3 + ["national"] * 3)
    report = frame.tempo.coverage()
    assert report.columns[0] == f"{TERR}_nivel"
    assert set(report[f"{TERR}_nivel"]) == {"judet", "national"}


def test_coverage_omits_the_level_when_there_is_only_one():
    report = tidy_frame().tempo.coverage()
    assert f"{TERR}_nivel" not in report.columns
    assert report.columns[0] == TERR


def test_coverage_prefers_the_clean_name_column():
    frame = tidy_frame()
    frame[f"{TERR}_nume"] = frame[TERR].str.upper()
    report = frame.tempo.coverage()
    assert f"{TERR}_nume" in report.columns
    assert set(report[f"{TERR}_nume"]) == {"ALBA", "CLUJ"}


# ------------------------------------------- homonyms, keyed on SIRUTA

LOC = "Localitati"


def locality_frame():
    """Two communes sharing a name in different counties, as Romania has.

    ALBAC in Alba and ALBAC in Cluj are different places with different SIRUTA
    codes. Grouping by name would merge them into one invented series.
    """
    frame = pd.DataFrame({
        "Judete": ["Alba", "Alba", "Cluj", "Cluj"],
        LOC: ["2130 ALBAC", "2130 ALBAC", "5555 ALBAC", "5555 ALBAC"],
        "Ani": ["Anul 2020", "Anul 2021", "Anul 2020", "Anul 2021"],
        "Valoare": [10.0, 20.0, 100.0, 200.0],
        "Judete_nivel": ["judet"] * 4,
        f"{LOC}_siruta": [2130, 2130, 5555, 5555],
        f"{LOC}_nivel": ["localitate"] * 4,
        f"{LOC}_nume": ["ALBAC"] * 4,
        "Ani_an": [2020, 2021, 2020, 2021],
    })
    return frame


def test_coverage_keeps_homonyms_apart():
    report = locality_frame().tempo.coverage()

    assert len(report) == 2, "two communes sharing a name are two units"
    assert sorted(report[f"{LOC}_siruta"]) == [2130, 5555]
    # each series stays its own: no min from one place and max from the other
    alba = report[report[f"{LOC}_siruta"] == 2130].iloc[0]
    cluj = report[report[f"{LOC}_siruta"] == 5555].iloc[0]
    assert (alba["min_value"], alba["max_value"]) == (10.0, 20.0)
    assert (cluj["min_value"], cluj["max_value"]) == (100.0, 200.0)


def test_coverage_shows_the_name_and_the_county_as_labels():
    report = locality_frame().tempo.coverage()
    assert list(report[f"{LOC}_nume"]) == ["ALBAC", "ALBAC"]
    # the county is what tells them apart by eye
    assert "Judete" in report.columns
    assert sorted(report["Judete"]) == ["Alba", "Cluj"]


def test_coverage_uses_the_level_of_the_grouped_dimension():
    """Not another dimension's level: units here are localities."""
    frame = locality_frame()
    frame["Judete_nivel"] = ["judet", "judet", "national", "national"]
    frame[f"{LOC}_nivel"] = ["localitate", "localitate", "national", "national"]
    report = frame.tempo.coverage()
    assert report.columns[0] == f"{LOC}_nivel"
    assert "Judete_nivel" not in report.columns


def test_coverage_falls_back_to_the_original_column_without_siruta():
    """No SIRUTA anywhere: group on the original label, never on the name."""
    frame = locality_frame().drop(columns=[f"{LOC}_siruta"])
    report = frame.tempo.coverage()
    # the original labels still carry the code, so the two stay apart
    assert len(report) == 2
    assert f"{LOC}_siruta" not in report.columns


def test_coverage_row_count_matches_distinct_units():
    frame = locality_frame()
    assert len(frame.tempo.coverage()) == frame[f"{LOC}_siruta"].nunique()


# -------------------------------------------------------------------- geo

def test_geo_is_a_documented_stub():
    with pytest.raises(NotImplementedError) as info:
        tidy_frame().tempo.geo()
    assert "SIRUTA" in str(info.value)
    assert "pytempo[geo]" in str(info.value)
