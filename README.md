# pytempo

**Status: still under test.** The library works end to end and is covered by
tests, but it has not been through real use yet. Expect rough edges, and check
results against the INS site before you rely on them.

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

    t.find("salariati")           # plain keyword search, instant
    t.search("salariati", level="localitate")   # discovery with filters
    t.search(level="localitate")  # filters work with no keyword at all
    t.search(domeniu="economic", periodicitate="lunar", caen=True)
    t.filters()                   # which filters exist and what they accept
    t.build_index()               # metadata index, once, then filters are instant
    t.domains()                   # the 8 top level statistical domains

    m = t.matrix("FOM104D")       # fetch one indicator's metadata
    m.show()                      # short summary
    m.describe()                  # the full record, every word INS wrote
    m.options()                   # which dimensions it has, and how big
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

Both return every match. They are lists, so slice them, or pass `limit=N`.

`find(level=...)` keeps only the indicators that reach that territorial level,
filtering from a local index, so it is instant and touches no network.

### The metadata index

Levels, periodicity, CAEN and domain are only known from an indicator's
metadata, so answering "which indicators reach locality level" needs metadata
for the whole catalogue. That is built once and cached on disk:

    t.build_index()

It walks all 1916 indicators at roughly 0.4 seconds each, so about 13 minutes
the first time, shows progress as it goes, and writes `data/levels_index.json`
as one record per code:

    {"FOM104D": {"levels": [...], "periodicity": ["Anuala"],
                 "has_caen": false, "domain": "A. STATISTICA SOCIALA"}}

Indicators whose metadata fails are skipped and reported rather than aborting
the build. Pass `refresh=True` to rebuild, `confirm=False` to skip the prompt,
`progress=False` to stay quiet.

Because it is expensive, `build_index()` asks before it starts, once. If you
use a metadata filter and no index exists, it asks you then. Decline and you
get an empty result plus a note, never a silent multi minute stall. An index
written by an older version simply lacks the newer fields: filters on those
fields match nothing and you get a line telling you to rebuild, rather than a
crash or a surprise rebuild.

A quick check that the live endpoints answer:

    python examples/check_links.py

## Navigating

Finding an indicator. `find` and `search` are different tools: `find` is the
plain keyword search, no filters, answered instantly from the name index.
`search` is discovery with filters, and its keyword is optional.

    t.find('salariati')          plain keyword search, in name or code
    t.search('salariati', level='localitate')   keyword plus a filter
    t.search(level='localitate') filter alone, across the whole catalogue
    t.filters()                  which filters exist and what they accept
    t.build_index()              the metadata index, once, a few minutes

`search` takes four filters, all optional, all combinable with each other and
with the keyword:

    level='judet'            territorial level
    caen=True                only those with a CAEN dimension, False only those without
    domeniu='economic'       substring of the domain name, diacritics ignored
    periodicitate='lunar'    substring of the periodicity, diacritics ignored

    t.search(domeniu='economic', periodicitate='lunar', level='judet')

The substring filters are deliberately forgiving: `economic` matches
`B. STATISTICA ECONOMICA`, so you do not have to know the exact wording.
`t.filters()` prints the real values available, read from the index.
    t.domains()                  the 8 top level statistical domains
    t.overview()                 how big the catalogue is and where to start

Understanding an indicator:

    m = t.matrix('FOM104D')      fetch the metadata
    m.what()                     what it measures, in a few lines
    m.where()                    where it sits and what it covers
    m.how()                      its own download manual, ready to copy
    m.show()                     short summary: domain, levels, dimensions
    m.describe()                 the full record, every word INS wrote
    t.info('FOM104D')            the same metadata, as a dict
    m.where()                    the domain breadcrumb
    m.related()                  the other indicators under the same node
    m.levels                     levels, e.g. ['national', 'judet', 'localitate']
    m.has_siruta                 True when localities carry a SIRUTA prefix
    m.options()                  which dimensions it has, role and size
    m.options('teritoriu')       what values one dimension can take
    m.help()                     this guide, for one indicator

`show()` is the summary you read while browsing. `describe()` is the full
record: the domain breadcrumb, levels, periodicity, last update, then the
complete definition, methodology, sources and observations, untruncated. Read
it before you trust a series. FOM104D's observations are where INS notes that
1990 is only available at county total level, and definitions run to several
thousand characters.

Pulling the data:

    df = m.get()                 the finest level it reaches, cleaned up
    m.get(level='judet')         one territorial level only
    m.get(levels=['judet', 'regiune'])   several levels
    m.get(level=None)            every level at once
    m.get(raw=True)              exactly what INS returned, no derived columns
    m.get(progress=True)         report progress on large indicators
    t.get('FOM101A')             the same, starting from a code

Lists returned by `find`, `domains` and `related` render as a table, in the
terminal and in a notebook, and carry `.recent(n)`, which orders by last update
date. The table gains a `nivele` column when every row already knows its
levels, which is the case for `search` results filtered on metadata. Display
never costs a request, so a list where any row's levels are unknown, such as a
plain `find` or `domains`, stays at code and name. `.recent(n)` fetches metadata only for the items already in that list, so
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
`national`, `macroregiune`, `regiune`, `judet`, `localitate` and `necunoscut`.
Levels come from the option labels of a territorial dimension: `TOTAL` and
`Nivel National` are national, `MACROREGIUNEA ...` is a macroregion,
`REGIUNEA ...` is a region, and a county is a name that appears in the actual
list of Romanian counties. A confirmed locality dimension reports `localitate`
directly.

Anything else is `necunoscut`, and that is deliberate. Territorial dimensions
also carry names that are not administrative units at all: air quality
monitoring stations, multi county groupings such as `Arges, Valcea`,
`Extra-regiuni`, `Nespecificat`. Calling those counties, which is what a
catch all default does, quietly corrupts any analysis that groups by county.

A dimension counts as holding localities when `details.nomLoc` says so, or when
its label says so and either `matSiruta` is set or its options actually carry
SIRUTA prefixes. The label alone is not enough: TMP1173 has a dimension called
`Statii de monitorizare de tip fond urban - Localitate` whose options are
monitoring stations.

    t.matrix("FOM104D").levels   # ['national', 'judet', 'localitate']
    t.matrix("SOM101B").levels   # ['national', 'macroregiune', 'regiune', 'judet']

`m.options(dimension)` accepts a dimension index, a label such as `Judete`, a
role such as `timp`, a level such as `judet` or `localitate`, or `teritoriu`
for the finest territorial dimension present.

### The shape of the data

`m.get()` executes the indicator's `fetch_plan`: it reads the strategy, runs it,
and applies tidy. Nothing is decided at request time. It returns a long format
DataFrame: one text column per dimension, in `dimensionsMap` order, a numeric
`Valoare` column, and the derived columns.

By default `get()` takes the finest territorial level the indicator actually
reaches, because a territorial dimension normally mixes the country total,
macroregions, regions and counties in one column and you rarely want them
stacked together. It prints one line saying what it decided before it starts.

    m.get()                               # the finest level, cleaned up
    m.get(level="judet")                  # counties only, no TOTAL, no regions
    m.get(levels=["judet", "regiune"])    # both
    m.get(level=None)                     # everything, the old default
    m.get(raw=True)                       # no derived columns

Indicators with no usable territorial level get no filter at all and `get()`
returns everything: that covers the 1362 non territorial ones, and the handful
whose territorial names are not administrative units. Indicators that keep
county and locality as two separate dimensions are downloaded whole, county by
county, which already delivers the locality level.

Naming a level the indicator does not have raises `ValueError`, lists the
levels it does have, and suggests the closest one, so a typo is cheap:

    t.matrix("FOM101A").get(level="judete")
    ValueError: nivel necunoscut 'judete' la FOM101A. Posibile: national,
    macroregiune, regiune, judet. Poate ai vrut 'judet'?

`search(level=...)` raises the same shape of message against the full list of
levels. Level arguments are typed as a `Literal`, so editors offer the valid
values as you type, and `t.filters()` lists them on demand. Indicators built with county and locality as two separate
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
work. Every indicator is downloadable; large ones just take more requests.

Indicators that carry a locality dimension are downloaded one county at a time,
using `parentId`, which ties a locality to its county. The county dimension is
narrowed to that same county for each request, so a request covers one county
and its own localities rather than the mostly empty product of all counties
against a few localities. FOM104D takes 43 requests this way.

Everything else is split on its largest dimension, in pieces sized by how much
room the other dimensions leave, and the split recurses onto the next dimension
when even a single option does not fit. The frames are concatenated with
`ignore_index=True`.

    df = t.matrix("FOM106E").get(progress=True)

`progress="auto"`, the default, reports each request only when there is more
than one. Above 50 requests `get()` asks before starting, since that is minutes
of work; pass `confirm=False` in scripts.

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

## Internals: the schema registry

`pytempo/schemas/registry.json` is a census of the whole catalogue, one record
per indicator: its dimensions with their roles and sizes, levels, family, total
cell count, periodicity, domain, and whether it carries SIRUTA. It ships inside
the package and is versioned in the repo, so a fresh clone already has the map
and the metadata filters in `search` work without waiting for a build. Fetching
the metadata is also the endpoint test: `status` is `ok` only if the endpoint
answered.

The file is written sorted and indented, so a change on the INS side shows up
as a readable git diff rather than one long line. It carries
`registry_version`, and an unknown version raises a clear error instead of
failing somewhere deeper.

`family` is what will decide how data gets fetched:

    judet_localitate    has a locality dimension, needs county by county
    teritorial_caen     territorial plus CAEN, no localities
    teritorial_simplu   territorial, no CAEN, no localities
    neteritorial        no territorial dimension at all
    alt                 anything else, listed individually in the report

Nothing here is public API. Use it from a development shell:

    from pytempo import schemas

    schemas.build_registry()            # incremental: only codes not yet ok
    schemas.build_registry(refresh=True)  # rebuild everything, bypass the cache
    schemas.report()                    # reprint the census, no rebuild

`build_registry()` is incremental by default: it adds codes missing from the
registry and leaves the rest untouched. That means it does not notice an
indicator INS has changed, because it does not re-read its metadata. Use
`refresh=True` for that. It asks before doing work that needs uncached
metadata, and skips the question when the local cache already covers it.

The report prints the totals, the split by family and by domain, how many carry
SIRUTA, how many exceed the single request cell limit, and the full list of
codes classified `alt` or holding an error, with a reason each. After changing
anything that affects classification, rebuild and check the diff:

    git diff --stat pytempo/schemas/registry.json

### Fetch plans

Every `ok` entry carries a `fetch_plan`, precomputed so that fetching data is
execution rather than decision making: read the plan, run the strategy, apply
tidy. Nothing is worked out at request time.

    default_level   the finest level the indicator reaches, null if it has none
    strategy        single, by_county, or split:<dimension label>
    est_requests    how many POSTs the strategy will take
    tidy_ready      whether there is anything to standardize

`single` covers 1752 indicators, `by_county` 79, and `split` 85. The split
dimension is the largest one, chosen so each request stays under the cell
limit. Recompute the plans without touching the network:

    schemas.refresh_plans()

### Validating against real data

The registry says what should happen. Validation asks for a small real slice of
each indicator, a few dozen cells in a single POST, and checks what came back:
the CSV parses, the column count matches, values are numeric, SIRUTA appears
where the entry claims it should, no negative counts of persons, and a cell
picked out of the slice returns the same value when requested on its own.

    schemas.validate(sample=15, seed=42)   # stratified sample, minutes
    schemas.validate()                     # the whole catalogue, hours
    schemas.validate()                     # again: resume skips what passed

Sampling is stratified by family with a floor of three per family, so the small
families do not vanish behind the 71 percent that is `neteritorial`. Each
indicator gets `validated_at`, `validation` (`ok`, `empty`, or `error: what`)
and `slice_cells` written back, and `resume=True` skips anything already `ok`
at the same registry version, so the long run can be stopped and restarted.
`delay` spaces the requests out.

An empty result is recorded as `empty`, not as an error: a combination with no
data is a legitimate answer.

Finally, a list to check by hand:

    schemas.spot_check_list(5)

This is deliberately manual. The TEMPO site and the API are the same system, so
comparing them automatically would compare the API with itself and always
agree. A human reading the site is the only independent check, so the job here
is to hand them a ready made list of cells, each with the indicator URL.

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
* Document only what exists and works. Keep roadmap notes out of this file.

## License

MIT.
