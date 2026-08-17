"""Offline tests at the scale that actually broke: POP107D, county by county.

The structure is the real one. tests/fixtures/POP107D_meta.json is the answer
of matrix/POP107D, saved once: 104 ages, 3 sexes, 43 counties, 3182 localities
with their parentId, 35 years. Nothing here touches the network; the metadata
comes from the file and pivot is mocked.

That structure is what matters: it is what turns one call into a plan of dozens
of requests, split county by county and, inside the biggest counties, split
again on the age dimension. A synthetic matrix would not reproduce that, and it
is exactly the case that ran for five hours and was abandoned.

The mock answers with rows built from the ids of the request itself, so every
slice is distinguishable, and it answers sparsely, the way INS does: a locality
appears only alongside the county that is its parent. The value of a row is a
function of the row, not of the request that carried it, which is what lets the
same data be asked for in one request or in fifty and compared.
"""
import json
from pathlib import Path

import pandas as pd

import pytempo as t
from pytempo import catalog, chunking, client, endpoints, incremental

FIXTURE = Path(__file__).parent / "fixtures" / "POP107D_meta.json"
POP107D = json.loads(FIXTURE.read_text(encoding="utf-8"))

VARSTE = "Varste si grupe de varsta"
JUDETE = "Judete"
LOCALITATI = "Localitati"
ANI = "Ani"

# small enough that the plan splits into dozens of requests, and that some
# counties are split a second time
MAX_CELLS_MIC = 1_000_000
# past the 1.49 billion cells of the whole indicator: one single request
MAX_CELLS_MARE = 2_000_000_000


def _matrix(monkeypatch):
    """POP107D built from the saved metadata, with no network at all."""
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": "POP107D", "name": "Populatia"}])

    def fake_get_json(url, **kw):
        assert url == endpoints.matrix("POP107D"), url
        return POP107D

    monkeypatch.setattr(client, "get_json", fake_get_json)
    return t.matrix("POP107D")


def _index_of(m, label: int | str) -> int:
    return [i for i, d in enumerate(m.dimensions)
            if d.label.strip() == label][0]


def _kept(m) -> dict:
    """The slice of the indicator the mock has data for.

    Fixed sets of ids, never positions: each request sees only part of the
    indicator, and a rule based on position would pick different rows in a
    request than in the whole. Ages are left whole, since that is the
    dimension select trims later on.
    """
    localitati = m.dimensions[_index_of(m, LOCALITATI)].options
    sexe = m.dimensions[_index_of(m, "Sexe")].options
    ani = m.dimensions[_index_of(m, ANI)].options
    return {
        "localitati": {o.nom_item_id for o in localitati[::30]},
        "sexe": {o.nom_item_id for o in sexe
                 if o.label.strip() == "Masculin"},
        "ani": {o.nom_item_id for o in ani if o.label.strip() == "Anul 2024"},
        "parinte": {o.nom_item_id: o.parent_id for o in localitati},
        "etichete": [{o.nom_item_id: o.label.strip() for o in d.options}
                     for d in m.dimensions],
        "pozitii": {"varste": _index_of(m, VARSTE),
                    "sexe": _index_of(m, "Sexe"),
                    "judete": _index_of(m, JUDETE),
                    "localitati": _index_of(m, LOCALITATI),
                    "ani": _index_of(m, ANI)},
    }


def _value(row) -> float:
    """A number that depends on the row and on nothing else.

    Deriving it from the encQuery instead would make the same row carry
    different numbers depending on how the download was cut, and there would be
    nothing left to compare one request against fifty.
    """
    varsta, sex, judet, localitate, an = row[:5]
    mix = varsta * 31 + sex * 17 + judet * 7 + localitate * 3 + an
    return float(mix % 1_000_000) + 0.5


def _rows_for(payload: dict, kept: dict) -> list[tuple]:
    """The rows INS would return for one request, as ids.

    Sparse on purpose: a locality only ever appears next to the county that is
    its parent. Pairing every county with every locality is what the real API
    does not do, and a mock that did would hide the bug it is meant to catch.
    """
    ids = [[int(x) for x in block.split(",")]
           for block in payload["encQuery"].split(":")]
    pos = kept["pozitii"]
    judete = set(ids[pos["judete"]])
    rows = []
    for varsta in ids[pos["varste"]]:
        for sex in ids[pos["sexe"]]:
            if sex not in kept["sexe"]:
                continue
            for localitate in ids[pos["localitati"]]:
                if localitate not in kept["localitati"]:
                    continue
                judet = kept["parinte"].get(localitate)
                if judet not in judete:
                    continue
                for an in ids[pos["ani"]]:
                    if an in kept["ani"]:
                        rows.append((varsta, sex, judet, localitate, an))
    return rows


def _csv_for(payload: dict, m, kept: dict) -> str:
    """One request's rows, in the CSV shape pivot answers with."""
    header = ", ".join([d.label.strip() for d in m.dimensions] + ["Valoare"])
    etichete = kept["etichete"]
    pos = kept["pozitii"]
    um = [int(x) for x in payload["encQuery"].split(":")[-1].split(",")][0]

    lines = [header]
    for row in _rows_for(payload, kept):
        pe_dimensiune = [None] * len(m.dimensions)
        pe_dimensiune[pos["varste"]] = etichete[pos["varste"]][row[0]]
        pe_dimensiune[pos["sexe"]] = etichete[pos["sexe"]][row[1]]
        pe_dimensiune[pos["judete"]] = etichete[pos["judete"]][row[2]]
        pe_dimensiune[pos["localitati"]] = etichete[pos["localitati"]][row[3]]
        pe_dimensiune[pos["ani"]] = etichete[pos["ani"]][row[4]]
        pe_dimensiune[len(m.dimensions) - 1] = etichete[-1][um]
        lines.append(", ".join(pe_dimensiune + [f"{_value(row)}"]))
    return "\n".join(lines) + "\n"


def _serve(monkeypatch, m, kept):
    """pivot, answered from the ids of each request. Returns the payload log."""
    cereri = []

    def fake_post(payload, **kw):
        cereri.append(payload)
        return _csv_for(payload, m, kept)

    monkeypatch.setattr(client, "post_pivot", fake_post)
    return cereri


def _keep_slices(monkeypatch):
    monkeypatch.setattr(incremental, "_clean_up",
                        lambda paths, folder, temporary, destination: None)


def _key(df, m) -> pd.DataFrame:
    """The frame keyed and ordered, so two downloads can be compared."""
    coloane = [d.label.strip() for d in m.dimensions]
    return (df.sort_values(coloane + ["Valoare"])
              .reset_index(drop=True))


def _grupele_de_varsta(m) -> list[str]:
    """Total plus the eighteen five year groups, without the 85 single ages.

    INS indents the single ages one level deeper than the groups, which is the
    only thing in the metadata that tells them apart.
    """
    varste = m.dimensions[_index_of(m, VARSTE)].options
    return [o.label.strip() for o in varste
            if not o.label.startswith("      ")]


# --------------------------------------------------------- the structure

def test_the_fixture_is_the_real_pop107d(monkeypatch):
    m = _matrix(monkeypatch)
    assert [(d.label.strip(), len(d.options)) for d in m.dimensions] == [
        (VARSTE, 104), ("Sexe", 3), (JUDETE, 43), (LOCALITATI, 3182),
        (ANI, 35), ("UM: Numar persoane", 1)]
    assert m.levels == ["national", "judet", "localitate"]
    assert m.has_siruta is True
    # 104 ages are 19 groups plus 85 single years
    assert len(_grupele_de_varsta(m)) == 19


def test_the_plan_is_dozens_of_requests(monkeypatch):
    """1.49 billion cells: county by county, and the big counties split again."""
    m = _matrix(monkeypatch)
    selectie = [[o.nom_item_id for o in d.options] for d in m.dimensions]
    assert chunking.cells(selectie) > 1_000_000_000

    plan = chunking.plan_requests(m, selectie, max_cells=MAX_CELLS_MIC)
    assert len(plan) > 40
    # one county per request, and every one of them under the threshold
    for payload in plan:
        blocuri = [b.split(",") for b in payload["encQuery"].split(":")]
        produs = 1
        for bloc in blocuri:
            produs *= len(bloc)
        assert produs <= MAX_CELLS_MIC
    judete = {p["encQuery"].split(":")[2] for p in plan}
    assert len(judete) == 43


# ------------------------------------------------- the download at scale

def test_every_planned_slice_is_written(monkeypatch, tmp_path):
    m = _matrix(monkeypatch)
    kept = _kept(m)
    monkeypatch.setattr(chunking, "MAX_CELLS", MAX_CELLS_MIC)
    cereri = _serve(monkeypatch, m, kept)
    _keep_slices(monkeypatch)

    folder = tmp_path / "pop107d"
    df = t.matrix("POP107D").download(folder=folder, progress=False)

    felii = [p for p in folder.iterdir() if p.name.startswith("_chunk_")]
    assert len(felii) == len(cereri) > 40
    assert df.attrs["complete"] is True


def test_nothing_lost_nothing_doubled(monkeypatch, tmp_path):
    m = _matrix(monkeypatch)
    kept = _kept(m)
    monkeypatch.setattr(chunking, "MAX_CELLS", MAX_CELLS_MIC)
    cereri = _serve(monkeypatch, m, kept)

    df = t.matrix("POP107D").download(folder=tmp_path / "d", progress=False)

    # the checks that run inside download() found nothing to say
    assert df.attrs["aggregation_warnings"] == []
    # and the same thing again from outside: rows are the sum of the slices,
    # and no combination of dimensions occurs twice
    asteptate = sum(len(_rows_for(p, kept)) for p in cereri)
    assert len(df) == asteptate > 5000
    coloane = [d.label.strip() for d in m.dimensions]
    assert int(df.duplicated(coloane).sum()) == 0


def test_every_slice_lands_whole_and_in_place(monkeypatch, tmp_path):
    """Each request is found in the result, row by row, value by value."""
    m = _matrix(monkeypatch)
    kept = _kept(m)
    monkeypatch.setattr(chunking, "MAX_CELLS", MAX_CELLS_MIC)
    cereri = _serve(monkeypatch, m, kept)

    df = t.matrix("POP107D").download(folder=tmp_path / "d", progress=False)

    etichete = kept["etichete"]
    pos = kept["pozitii"]
    gasite = {
        (r[VARSTE], r["Sexe"], r[JUDETE], r[LOCALITATI], r[ANI]): r["Valoare"]
        for r in df.to_dict("records")
    }
    assert len(gasite) == len(df)

    for payload in cereri:
        for row in _rows_for(payload, kept):
            cheie = (etichete[pos["varste"]][row[0]],
                     etichete[pos["sexe"]][row[1]],
                     etichete[pos["judete"]][row[2]],
                     etichete[pos["localitati"]][row[3]],
                     etichete[pos["ani"]][row[4]])
            assert gasite[cheie] == _value(row)


def test_the_derived_columns_survive_the_scale(monkeypatch, tmp_path):
    """tidy runs on the joined frame, so SIRUTA and the year are there once."""
    m = _matrix(monkeypatch)
    kept = _kept(m)
    monkeypatch.setattr(chunking, "MAX_CELLS", MAX_CELLS_MIC)
    _serve(monkeypatch, m, kept)

    df = t.matrix("POP107D").download(folder=tmp_path / "d", progress=False)
    assert f"{LOCALITATI}_siruta" in df.columns
    assert f"{JUDETE}_nivel" in df.columns
    assert set(df[f"{ANI}_an"].unique()) == {2024}
    # every locality row carries a SIRUTA code, the county TOTAL row does not
    fara_cod = df[df[f"{LOCALITATI}_siruta"].isna()]
    assert set(fara_cod[LOCALITATI]) == {"TOTAL"}


# ------------------------------------------------------------ equivalence

def test_one_request_and_fifty_agree(monkeypatch, tmp_path):
    """The proof that cutting and joining at scale changes nothing.

    The same indicator, asked for in a single request and in dozens, has to
    come back as the same frame once both are sorted.
    """
    m = _matrix(monkeypatch)
    kept = _kept(m)

    monkeypatch.setattr(chunking, "MAX_CELLS", MAX_CELLS_MARE)
    cereri = _serve(monkeypatch, m, kept)
    intreg = t.matrix("POP107D").download(folder=tmp_path / "unu",
                                          progress=False)
    assert len(cereri) == 1

    monkeypatch.setattr(chunking, "MAX_CELLS", MAX_CELLS_MIC)
    cereri = _serve(monkeypatch, m, kept)
    bucati = t.matrix("POP107D").download(folder=tmp_path / "multe",
                                          progress=False)
    assert len(cereri) > 40

    pd.testing.assert_frame_equal(_key(bucati, m), _key(intreg, m))


def test_download_and_get_agree_at_scale(monkeypatch, tmp_path):
    """And through disk or through memory, still the same frame."""
    m = _matrix(monkeypatch)
    kept = _kept(m)
    monkeypatch.setattr(chunking, "MAX_CELLS", MAX_CELLS_MIC)
    _serve(monkeypatch, m, kept)

    prin_disc = t.matrix("POP107D").download(folder=tmp_path / "d",
                                             progress=False)
    prin_memorie = t.matrix("POP107D").get(progress=False, confirm=False)
    pd.testing.assert_frame_equal(_key(prin_disc, m), _key(prin_memorie, m))


# --------------------------------------------- the case from the field

def test_select_on_the_age_groups(monkeypatch, tmp_path):
    """The real workaround: the 19 groups, not the 85 single ages.

    The filter check has to pass on exactly 19 distinct values, and cutting the
    download into slices still has to give what a single request gives.
    """
    m = _matrix(monkeypatch)
    kept = _kept(m)
    grupe = _grupele_de_varsta(m)
    assert len(grupe) == 19 and grupe[0] == "Total"

    monkeypatch.setattr(chunking, "MAX_CELLS", MAX_CELLS_MIC)
    cereri = _serve(monkeypatch, m, kept)
    bucati = t.matrix("POP107D").download(select={"varst": grupe},
                                          folder=tmp_path / "multe",
                                          progress=False)
    assert len(cereri) > 40
    # the filter arrived, and came back the size it was asked for
    assert bucati.attrs["aggregation_warnings"] == []
    assert bucati[VARSTE].nunique() == 19
    assert not any(v.startswith("      ") for v in bucati[VARSTE])

    monkeypatch.setattr(chunking, "MAX_CELLS", MAX_CELLS_MARE)
    cereri = _serve(monkeypatch, m, kept)
    intreg = t.matrix("POP107D").download(select={"varst": grupe},
                                          folder=tmp_path / "unu",
                                          progress=False)
    assert len(cereri) == 1
    pd.testing.assert_frame_equal(_key(bucati, m), _key(intreg, m))


def test_a_select_the_server_ignores_is_caught(monkeypatch, tmp_path, capsys):
    """If the filter did not reach the query, the check says so.

    The mock answers with every age whatever was asked for, which is what a
    server that ignored encQuery would do.
    """
    m = _matrix(monkeypatch)
    kept = _kept(m)
    grupe = _grupele_de_varsta(m)
    toate_varstele = [o.nom_item_id
                      for o in m.dimensions[_index_of(m, VARSTE)].options]

    monkeypatch.setattr(chunking, "MAX_CELLS", MAX_CELLS_MIC)

    def fake_post(payload, **kw):
        blocuri = payload["encQuery"].split(":")
        blocuri[_index_of(m, VARSTE)] = ",".join(str(i) for i in toate_varstele)
        return _csv_for(dict(payload, encQuery=":".join(blocuri)), m, kept)

    monkeypatch.setattr(client, "post_pivot", fake_post)
    df = t.matrix("POP107D").download(select={"varst": grupe},
                                      folder=tmp_path / "d", progress=False)

    assert df[VARSTE].nunique() == 104
    avertismente = df.attrs["aggregation_warnings"]
    assert any(w.startswith("SELECT") and "did not reach the query" in w
               for w in avertismente)
    assert "SELECT" in capsys.readouterr().out
