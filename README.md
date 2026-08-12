# pytempo

A Python library for reading Romanian official statistics from the INS TEMPO
Online API. It has one job: talk to the INS API well. No database, no SIRUTA
enrichment, no Postgres loader. Those live in separate downstream projects that
import this library.

## Install

The import name is `pytempo`. Install straight from GitHub:

    pip install git+https://github.com/CIDS-UBB/pytempo.git

then:

    import pytempo as t

A note on PyPI: the name `pytempo` is already taken there by an unrelated Web3
extension, so the distribution name is `pytempo-ins`. The GitHub install above
gives you `import pytempo` either way. If this is ever published to PyPI it will
be `pip install pytempo-ins`, still with `import pytempo`.

## Quickstart

    import pytempo as t

    t.overview()                  # how big the catalogue is and where to start
    t.help()                      # the navigation guide, same content as below

    t.find("salariati")           # search by keyword, in name or code
    t.find("salariati", level="localitate")   # only those reaching localities
    t.search("someri", limit=5)   # the same thing, longer name
    t.domains()                   # the 8 top level statistical domains

    m = t.matrix("FOM104D")       # fetch one indicator's metadata
    m.show()                      # readable summary
    m.levels                      # ['national', 'judet', 'localitate']
    m.has_siruta                  # True when locality labels carry a SIRUTA prefix
    m.where()                     # A. STATISTICA SOCIALA > FORTA DE MUNCA > SALARIATI
    m.related()                   # the other indicators under the same node
    m.options("Judete")           # what values that dimension can take

    df = t.matrix("FOM101A").get()             # the data, long format
    df = t.matrix("FOM101A").get(level="judet")  # counties only

    t.info("FOM104D")             # the same metadata as a plain dict
    t.load_index()                # every indicator: [{code, name}, ...]
    t.name_dict()                 # {code: name}

Search matches all the words you give it, in the name or the code, case
insensitively and ignoring Romanian diacritics, so `someri` finds `Șomerii`.

`find(level=...)` keeps only the indicators that reach that territorial level.
Be aware of the cost: levels are only known from an indicator's metadata, so
this fetches metadata for each name match in turn, one request each, until it
has `limit` results that pass. Without `level`, search answers instantly from
the name index and fetches nothing. Because the survivors already carry their
metadata, their levels are available without further requests.

A quick check that the live endpoints answer:

    python examples/check_links.py

## Navigating

Finding an indicator:

    t.find('salariati')          search by keyword, in name or code
    t.find('salariati', level='localitate')   only those reaching localities
    t.search('someri', limit=5)  the same thing, longer name
    t.domains()                  the 8 top level statistical domains
    t.overview()                 how big the catalogue is and where to start

Understanding an indicator:

    m = t.matrix('FOM104D')      fetch the metadata
    m.show()                     readable summary: domain, levels, dimensions
    t.info('FOM104D')            the same metadata, as a dict
    m.where()                    the domain breadcrumb
    m.related()                  the other indicators under the same node
    m.levels                     levels, e.g. ['national', 'judet', 'localitate']
    m.has_siruta                 True when localities carry a SIRUTA prefix
    m.options('teritoriu')       what values a dimension can take
    m.help()                     this guide, for one indicator

Pulling the data:

    df = m.get()                 all of it, as a long format DataFrame
    m.get(level='judet')         one territorial level only
    m.get(levels=['judet', 'regiune'])   several levels
    m.get(tidy=True)             plus derived columns: SIRUTA, level, type, year
    m.get(progress=True)         report progress on large indicators
    t.get('FOM101A')             the same, starting from a code

Lists returned by `find`, `domains` and `related` render as a table, in the
terminal and in a notebook, and carry `.recent(n)`, which orders by last update
date. `.recent(n)` fetches metadata only for the items already in that list, so
keep the list small. There is no catalogue wide recent: it would take thousands
of requests.

### Dimension roles and territorial levels

Each dimension gets a role: `teritoriu`, `timp`, `caen`, `um` or `alt`. A
dimension counts as territorial if the `details` block says so, through
`nomJud`, `nomLoc` or `matRegJ` pointing at its `dimCode`, or if its label
mentions counties, localities, regions or macroregions. Both routes matter.
Indicators built on the county plus locality nomenclator, such as FOM104D,
are marked in `details`, but the common case is a single hierarchical
dimension holding macroregions, regions and counties together, and there
`details` is sometimes silent. `matTime` gives `timp`, and a label starting with `UM:` gives `um`.

CAEN works the same way, from either source: `matCaen1` or `matCaen2` pointing
at the `dimCode`, or the label containing `caen`. The label route is not
optional here either. FOM104F carries a dimension called
`CAEN Rev.2 (activitati ale economiei nationale)` while both CAEN flags in its
`details` are 0.

`m.levels` lists the territorial levels present, from coarse to fine, out of
`national`, `macroregiune`, `regiune`, `judet` and `localitate`. Levels come
from the option labels of a territorial dimension: `TOTAL` is national,
`MACROREGIUNEA ...` is a macroregion, `REGIUNEA ...` is a region, anything else
is a county. A locality dimension reports `localitate` directly.

    t.matrix("FOM104D").levels   # ['national', 'judet', 'localitate']
    t.matrix("SOM101B").levels   # ['national', 'macroregiune', 'regiune', 'judet']

`m.options(dimension)` accepts a dimension index, a label such as `Judete`, a
role such as `timp`, a level such as `judet` or `localitate`, or `teritoriu`
for the finest territorial dimension present.

### The shape of the data

`m.get()` posts every option of every dimension in one request and returns a
long format DataFrame: one text column per dimension, in `dimensionsMap` order,
plus a numeric `Valoare` column.

`level` or `levels` restrict the territorial dimension to the levels you name,
which is what you usually want, since a territorial dimension normally mixes
the country total, macroregions, regions and counties in one column:

    m.get(level="judet")                  # counties only, no TOTAL, no regions
    m.get(levels=["judet", "regiune"])    # both

Naming a level the indicator does not have raises `ValueError` and lists the
levels it does have. Indicators built with county and locality as two separate
dimensions, such as FOM104D, raise `NotImplementedError` rather than quietly
returning everything.

### Standardized columns

`get()` returns the data as INS serves it. `get(tidy=True)` adds derived columns
on top, and only adds: nothing is dropped, renamed or reordered, and the
original label keeps its SIRUTA prefix.

For every territorial dimension, using its label as the prefix, so two
territorial dimensions never collide:

    <label>_siruta    the SIRUTA code, Int64 nullable, NA for aggregates
    <label>_nivel     national, macroregiune, regiune, judet or localitate
    <label>_tip       municipiu, oras, comuna or sector, NA above locality
    <label>_nume      the name without the code and the type prefix

For every time dimension, `<label>_an` holds the year parsed out of labels like
`Anul 2024`, as Int64, NA when no year is present.

Locality labels arrive as `SIRUTA TYPE NAME`, for example
`1017 MUNICIPIUL ALBA IULIA` and `1151 ORAS ABRUD`. Communes carry no type
prefix, as in `2130 ALBAC`, and are typed `comuna`. Aggregates and counties
carry no SIRUTA at all.

### Large indicators

A single POST is capped at `MAX_CELLS`, currently 100000 cells, counted as the
product of the selected options per dimension. Above that, `get()` splits the
work instead of sending one doomed request.

Indicators that carry a locality dimension are downloaded one county at a time,
using `parentId`, which ties a locality to its county. The county dimension is
narrowed to that same county for each request, so a request covers one county
and its own localities rather than the mostly empty product of all counties
against a few localities. If a single county still exceeds the threshold, its
localities are split into groups of `COUNTY_CHUNK`, currently 100. The frames
are concatenated with `ignore_index=True`. FOM104D takes 43 requests this way.

    df = t.matrix("FOM104D").get(progress=True)

`progress=True` reports each request as it lands, with the row count and the
running total. Indicators that are over the threshold but have no locality
dimension to split by, such as SOM101B unfiltered, still raise `ValueError`,
which names the levels you can filter on instead.

The result is sparse. Combinations with no data are absent as whole rows, not
present as blanks, and this reflects real administrative history: Ilfov and
Municipiul Bucuresti do not appear before 1996, and the combined
`Mun. Bucuresti -incl. SAI` unit does not appear after 1995. So do not validate
a pull by counting rows against the cartesian product of the dimensions, and do
not assume a complete grid when reshaping.

Column names come from `matrix.dimensions`, not from the CSV header. The API
replaces commas inside a dimension label with spaces, so the header for
`Macroregiuni, regiuni de dezvoltare si judete` arrives with the comma gone.
The parser checks the column count against the number of dimensions plus one
and raises if they disagree, which is the guard against that fragility.

## Development

Install the library in editable mode, so your edits take effect without
reinstalling:

    pip install -e ".[dev]"

To use your working copy from another project while you develop, install it
editable into that project's own environment, pointing at your local path:

    pip install -e C:/PROJECTS/Tempo/pytempo

In a notebook, reload edited modules without restarting the kernel:

    %load_ext autoreload
    %autoreload 2

## Contributing

    git clone https://github.com/CIDS-UBB/pytempo.git
    cd pytempo
    pip install -e ".[dev]"
    pytest -q
    python -m build

The tests run offline against fixtures, so they need no network.

Style rules:

* No em dash or en dash, anywhere: code, comments, docs.
* Small modules with one job each. Do not inflate the structure.
* Every URL lives in `endpoints.py`. Do not hardcode one anywhere else.
* When you add a method, update `t.help()` and this README in the same commit.
* Document only what exists and works. Roadmap notes belong in SPEC.md.

## License

MIT.
