"""Offline tests that pin the request plans, payload for payload. No network.

tests/fixtures/plans_before_chains.json was generated from the planner as it
stood before chains of dimensions linked by parentId were recognized, on real
metadata, one matrix per branch:

    SCL101B   under MAX_CELLS, a single request
    FOM104F   over it, no localities, no chains: the blind split
    FOM104D   localities, county and locality as separate dimensions
    GOS102A   localities named 'Municipii si orase'
    TUR101C   localities, by county
    POP107D   localities, a county that still does not fit is split further

Whatever changes in the planner, these plans must come out identical, not
equivalent: the same payloads, in the same order. A plan that asks for the same
cells in a different order would still change slice names, and with them what
resume finds on disk.

The second half covers the chains: INT109B, whose CAEN Rev.1 hierarchy is split
across five dimensions linked through parentId, planned one request per node
with children.
"""
import copy
import itertools
import json
from pathlib import Path

import pytest

import pytempo as t
from pytempo import catalog, chunking, client, endpoints

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "plans_before_chains.json").read_text(
    encoding="utf-8"))
CODES = sorted({key.split("|")[0] for key in GOLDEN})


def _api(monkeypatch, codes):
    meta = {cod: json.loads((FIXTURES / f"{cod}_meta.json").read_text(
        encoding="utf-8")) for cod in codes}
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": c, "name": f"Indicator {c}"} for c in meta])

    def fake_get_json(url, **kw):
        for cod, date in meta.items():
            if url == endpoints.matrix(cod):
                return date
        raise AssertionError(f"URL neasteptat: {url}")

    monkeypatch.setattr(client, "get_json", fake_get_json)


@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_plan_is_identical_to_the_one_before_chains(monkeypatch, key):
    cod, level = key.split("|")
    _api(monkeypatch, CODES)
    level = None if level == "None" else level
    _, _, _, requests = t.matrix(cod)._plan_requests(level, None, None)
    expected = GOLDEN[key]
    assert len(requests) == len(expected)
    for i, (got, want) in enumerate(zip(requests, expected)):
        assert got == want, f"{key}: payload {i} differs"


# ------------------------------------------- chains of dimensions (INT109B)

INT109B = json.loads((FIXTURES / "INT109B_meta.json").read_text(
    encoding="utf-8"))


def _int109b(monkeypatch, meta=None):
    """INT109B on its real metadata, or on a doctored copy of it."""
    meta = meta or INT109B
    monkeypatch.setattr(catalog, "_INDEX",
                        [{"code": "INT109B", "name": "Indicator INT109B"}])
    monkeypatch.setattr(client, "get_json",
                        lambda url, **kw: meta if url == endpoints.matrix(
                            "INT109B") else (_ for _ in ()).throw(
                            AssertionError(url)))
    return t.matrix("INT109B")


def _full(m):
    return [[o.nom_item_id for o in d.options] for d in m.dimensions]


def _blocks(payload):
    return [[int(c) for c in block.split(",")]
            for block in payload["encQuery"].split(":")]


def _consistent_tuples(m, chain):
    """Every path through the tree, completed with Total below: what INS has."""
    dims = m.dimensions
    totals = [next(o.nom_item_id for o in dims[k].options
                   if o.parent_id == o.nom_item_id) for k in chain[1:]]
    kids = {}
    for depth, k in enumerate(chain[1:], 1):
        for o in dims[k].options:
            if o.parent_id != o.nom_item_id:
                kids.setdefault((depth - 1, o.parent_id), []).append(
                    o.nom_item_id)
    out = set()

    def walk(path):
        out.add(tuple(path) + tuple(totals[len(path) - 1:]))
        for c in kids.get((len(path) - 1, path[-1]), []):
            walk(path + [c])

    for o in dims[chain[0]].options:
        walk([o.nom_item_id])
    return out


def test_int109b_has_a_five_dimension_chain(monkeypatch):
    m = _int109b(monkeypatch)
    assert chunking.find_chain(m) == [0, 1, 2, 3, 4]


def test_int109b_plans_one_request_per_node_with_children(monkeypatch):
    """283 requests where the blind split planned 9,127,800."""
    m = _int109b(monkeypatch)
    plan = chunking.plan_requests(m, _full(m))
    assert len(plan) == 283
    assert all(chunking.cells(_blocks(p)) <= chunking.MAX_CELLS for p in plan)
    assert len({p["encQuery"] for p in plan}) == len(plan)


def test_int109b_plan_asks_every_real_combination_exactly_once(monkeypatch):
    """No combination that exists is missed, none is asked twice, and no
    combination outside the tree is asked at all."""
    m = _int109b(monkeypatch)
    chain = chunking.find_chain(m)
    asked = []
    for p in chunking.plan_requests(m, _full(m)):
        blocks = _blocks(p)
        others = [blocks[i] for i in range(len(blocks)) if i not in chain]
        # the other dimensions are asked whole in every request
        assert others == [b for i, b in enumerate(_full(m)) if i not in chain]
        asked += list(itertools.product(*(blocks[k] for k in chain)))
    assert len(asked) == len(set(asked))
    assert set(asked) == _consistent_tuples(m, chain)
    assert len(asked) == 742


def test_chain_respects_a_narrowed_selection(monkeypatch):
    """One section asked: only its subtree, nothing from the others."""
    m = _int109b(monkeypatch)
    chain = chunking.find_chain(m)
    sel = _full(m)
    section = m.dimensions[0].options[0].nom_item_id
    sel[0] = [section]
    plan = chunking.plan_requests(m, sel, max_cells=1000)
    tuples = {tup for p in plan
              for tup in itertools.product(*(_blocks(p)[k] for k in chain))}
    assert tuples and all(tup[0] == section for tup in tuples)
    expected = {tup for tup in _consistent_tuples(m, chain)
                if tup[0] == section}
    assert tuples == expected


def test_chain_without_the_total_below_skips_the_aggregates(monkeypatch):
    """Classes as leaves only, no Total: the nodes above them cannot be asked
    in the form INS writes them, so they are not asked, as the product would
    not have asked them either."""
    m = _int109b(monkeypatch)
    chain = chunking.find_chain(m)
    sel = _full(m)
    sel[4] = [o.nom_item_id for o in m.dimensions[4].options
              if o.parent_id != o.nom_item_id]
    plan = chunking.plan_requests(m, sel)
    tuples = {tup for p in plan
              for tup in itertools.product(*(_blocks(p)[k] for k in chain))}
    assert len(tuples) == 460
    assert all(tup[4] in sel[4] for tup in tuples)


def test_a_partial_link_is_not_a_chain(monkeypatch):
    """One class with no parent left: the class dimension leaves the chain,
    and every class is still asked, under every group, by the plain split."""
    meta = copy.deepcopy(INT109B)
    classes = meta["dimensionsMap"][4]["options"]
    stray = next(o for o in classes if o["parentId"] != o["nomItemId"])
    stray["parentId"] = 999999999
    m = _int109b(monkeypatch, meta)
    assert chunking.find_chain(m) == [0, 1, 2, 3]
    plan = chunking.plan_requests(m, _full(m))
    asked_classes = {c for p in plan for c in _blocks(p)[4]}
    assert asked_classes == set(_full(m)[4])


def test_a_chain_without_its_totals_is_not_planned_as_one(monkeypatch):
    """No Total to put below a node means no way to ask for the aggregates in
    the form INS writes them: back to the plain split, which misses nothing."""
    meta = copy.deepcopy(INT109B)
    for dim in meta["dimensionsMap"][1:5]:
        dim["options"] = [o for o in dim["options"]
                          if o["parentId"] != o["nomItemId"]]
    m = _int109b(monkeypatch, meta)
    assert chunking.find_chain(m) is None


def test_the_registry_counts_the_chain_on_the_tree(monkeypatch):
    m = _int109b(monkeypatch)
    plan = m.fetch_plan()
    assert plan["strategy"] == "by_chain"
    assert plan["est_requests"] == 283
    assert chunking.chain_summary(m) == {
        "dims": [d.label.strip() for d in m.dimensions[:5]], "requests": 283}

