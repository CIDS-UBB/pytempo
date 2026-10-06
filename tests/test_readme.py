"""The README's examples, run against the code. Offline, on fixtures.

The README is the first thing anyone new reads, and the one part of the
library with no net under it: six of its examples had drifted from the code by
the time someone ran them one by one. These tests run the examples that are
deterministic and need no network, and compare what the README shows with what
the code prints.

What is not here, and why: examples whose output depends on downloaded data
(shapes, values, coverage, spot_check, the download progress lines) or on the
catalogue index in the local cache (find and search counts). Those stay
unchecked, and the test_readme_* names below are the full list of what is.

Where the README wraps a long line the code prints as one, the comparison is
on the words, with whitespace normalized. Where it shortens with '...', the
test compares what is shown and nothing past it.
"""
import contextlib
import io
import json
from pathlib import Path

import pytest

import pytempo as t
from pytempo import catalog, client, endpoints

from .test_smoke import FOM101A

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
README = (ROOT / "README.md").read_text(encoding="utf-8").split("\n")
META = {cod: json.loads((FIXTURES / f"{cod}_meta.json").read_text(
    encoding="utf-8")) for cod in ("TUR101B", "POP107D", "GOS102A", "SCL101B")}
META["FOM101A"] = FOM101A


def _api(monkeypatch):
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Indicator {c}"} for c in META])

    def fake_get_json(url, **kw):
        for cod, data in META.items():
            if url == endpoints.matrix(cod):
                return data
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(client, "get_json", fake_get_json)

    def no_data(*a, **k):
        raise AssertionError("an example under test must not fetch data")

    monkeypatch.setattr(client, "post_pivot", no_data)


def block_after(marker: str) -> list[str]:
    """The README code lines that follow the line `marker`, in its block.

    The block is the run of four space indented lines it sits in; the lines
    come back with that indent removed, blank lines inside the block kept.
    """
    hits = [i for i, line in enumerate(README) if line.strip() == marker
            and line.startswith("    ")]
    assert len(hits) == 1, f"{marker!r} found {len(hits)} times in the README"
    out = []
    for line in README[hits[0] + 1:]:
        if line.strip() and not line.startswith("    "):
            break
        out.append(line[4:])
    while out and not out[-1].strip():
        out.pop()
    return out


def printed(call) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        call()
    return out.getvalue()


def words(text) -> str:
    return " ".join(str(text).split())


# ------------------------------------------------------------------ how()

def test_readme_how_page_for_tur101b(monkeypatch):
    _api(monkeypatch)
    shown = block_after('t.matrix("TUR101B").how()')
    while shown and not shown[0].strip():
        shown.pop(0)
    real = printed(t.matrix("TUR101B").how).rstrip("\n").split("\n")
    assert [line.rstrip() for line in shown] == [line.rstrip() for line in real]


def test_readme_levels_table_for_pop107d(monkeypatch):
    """The table is cut out of POP107D's how() page."""
    _api(monkeypatch)
    shown = block_after("TERRITORIAL LEVEL, pick one:")
    page = printed(t.matrix("POP107D").how)
    for line in shown:
        assert line.strip() in page, line


def test_readme_filters_none_message(monkeypatch):
    """Territory and time only: GOS102A, whose single unit stays out."""
    _api(monkeypatch)
    hits = [i for i, line in enumerate(README)
            if line.strip().startswith("FILTERS: none to add.")]
    assert len(hits) == 1
    shown = README[hits[0]].strip() + " " + README[hits[0] + 1].strip()
    assert words(shown) in words(printed(t.matrix("GOS102A").how))


# --------------------------------------------- get() before any request

def test_readme_pop107d_too_large(monkeypatch):
    _api(monkeypatch)
    start = README.index("    POP107D: all levels, by_county, 380 requests")
    lines = []
    for line in README[start:]:
        if line.strip() and not line.startswith("    "):
            break
        lines.append(line[4:])
    shown = "\n".join(lines)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        with pytest.raises(t.MatrixTooLargeError) as info:
            t.matrix("POP107D").get()
    real = out.getvalue() + f"MatrixTooLargeError: {info.value}"
    assert words(shown) == words(real)


def test_readme_pop107d_select_announcement(monkeypatch):
    _api(monkeypatch)
    m = t.matrix("POP107D")
    shown = [line for line in block_after(
        "select={'varsta': ['0- 4 ani', '5- 9 ani'], 'Sexe': 'Masculin'})")
        if line.strip() and not line.startswith("df.shape")]
    with pytest.raises(AssertionError, match="must not fetch"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            m.get(level="judet", select={"varsta": ["0- 4 ani", "5- 9 ani"],
                                         "Sexe": "Masculin"})
    real = out.getvalue().strip().split("\n")
    assert [line.strip() for line in shown] == [line.strip() for line in real]


def test_readme_fom101a_announcement(monkeypatch):
    _api(monkeypatch)
    start = README.index("    FOM101A: level judet (the finest), single, "
                         "1 request")
    lines = []
    for line in README[start:]:
        if line.strip() and not line.startswith("    "):
            break
        lines.append(line)
    with pytest.raises(AssertionError, match="must not fetch"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            t.matrix("FOM101A").get()
    assert words("\n".join(lines)) == words(out.getvalue())


def test_readme_unknown_level_message(monkeypatch):
    _api(monkeypatch)
    shown = block_after('t.matrix("FOM101A").get(level="judete")')
    with pytest.raises(ValueError) as info:
        t.matrix("FOM101A").get(level="judete")
    assert words("\n".join(shown)) == words(f"ValueError: {info.value}")


def test_readme_flat_select_message(monkeypatch):
    _api(monkeypatch)
    shown = block_after("m.get(select={'Niveluri de educatie': 'groups'})")
    with pytest.raises(ValueError) as info:
        t.matrix("SCL101B").get(select={"Niveluri de educatie": "groups"})
    assert words("\n".join(shown)) == words(f"ValueError: {info.value}")


# ------------------------------------------------------- the metadata

def test_readme_options_of_gos102a(monkeypatch):
    _api(monkeypatch)
    shown = block_after("m.options()")
    real = printed(lambda: print(t.matrix("GOS102A").options()))
    assert [line.strip() for line in shown] == real.strip().split("\n")


def test_readme_territory_columns_of_gos102a(monkeypatch):
    _api(monkeypatch)
    shown = block_after("m.territory_columns()")
    assert eval(" ".join(shown)) == t.matrix("GOS102A").territory_columns()


def test_readme_sql_columns_of_gos102a(monkeypatch):
    _api(monkeypatch)
    shown = block_after('t.matrix("GOS102A").sql_columns()')
    assert eval(" ".join(shown)) == t.matrix("GOS102A").sql_columns()


def test_readme_age_groups_preview(monkeypatch):
    """Shortened with '...' in the README: the first ones, then the last."""
    _api(monkeypatch)
    m = t.matrix("POP107D")
    shown = block_after("m.options('varsta', kind='groups')   # see the 19 first")
    names = [n.strip() for n in shown[0].split(",")]
    cut = names.index("...")
    head, tail = names[:cut], names[cut + 1:]
    real = [str(x).strip() for x in m.options("varsta", kind="groups")]
    assert real[:len(head)] == head
    assert real[len(real) - len(tail):] == tail
    assert len(real) == 19


def test_readme_families_are_the_ones_the_code_has():
    start = README.index("    judet_localitate    has a locality dimension, "
                         "needs county by county")
    names = []
    for line in README[start:]:
        if not line.startswith("    "):
            break
        names.append(line.split()[0])
    from pytempo.schemas.classify import FAMILIES
    assert names == list(FAMILIES)


def test_readme_indentation_illustration(monkeypatch):
    """The three labels the README quotes are POP107D's, spaces and all."""
    _api(monkeypatch)
    start = README.index("    'Total'")
    shown = [eval(README[k].strip()) for k in range(start, start + 3)]
    labels = [o.label for o in
              t.matrix("POP107D")._find_dimension("varsta").options]
    for label in shown:
        assert label in labels, repr(label)
