# pytempo

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.18.0-informational.svg)](pyproject.toml)

A Python library for reading Romanian official statistics from the INS TEMPO
Online API.

Developed at the Center for Interdisciplinary Data Science, Babes-Bolyai
University.

**Status: still under test.** The library works end to end and is covered by
tests, but it has not been through real use yet. Check results against the INS
site before you rely on them.

## Install

The import name is `pytempo`. Install straight from GitHub:

    pip install git+https://github.com/CIDS-UBB/pytempo.git

A note on PyPI: the name `pytempo` is already taken there by an unrelated Web3
extension, so the distribution name is `pytempo-ins`. The GitHub install above
gives you `import pytempo` either way.

## Quickstart

    import pytempo as t

    t.find("salariati")                  # 104 indicators match
    t.search(level="localitate")         # 85 of them reach locality level

    m = t.matrix("FOM101A")
    m.what()                             # what it measures, in a few lines
    m.how()                              # its own download manual

    df = m.get()                         # (4392, 7), counties, tidied
    df.columns                           # ..., plus _nivel and Ani_an

`get()` prints what it decided before it starts, and names what the default
left out:

    FOM101A: level judet (the finest), single, 1 request
      for every level, including national, macroregiune and regiune,
      use get(level=None)

## Examples

Two guided notebooks in `examples/` walk through the library end to end,
identical in structure, one in English and one in Romanian. They run live
against INS and are saved with their outputs, so you can read them without
running anything:

    examples/tutorial_en.ipynb
    examples/tutorial_ro.ipynb

There is also `examples/check_links.py`, a quick script that confirms the live
endpoints answer.

## What it does

* **Finds indicators.** 1916 of them, searchable by keyword, or filtered by
  territorial level, domain, periodicity and whether they carry a CAEN
  classification.
* **Reads the metadata.** Definitions, methodology, sources and observations
  exactly as INS wrote them, plus the dimensions with their roles and sizes.
* **Fetches the data at any level.** From national totals down to localities,
  splitting large requests automatically so every indicator is downloadable.
* **Standardizes without destroying.** SIRUTA codes, territorial levels,
  locality types and years arrive as extra columns; the original labels stay
  untouched.
* **Ships a validated catalogue.** A registry of every indicator, its shape and
  its fetch plan, versioned in the repo, so filters work the moment you install.

## Navigating

`t.help()` prints the same guide as this section, from a Python prompt.

Finding an indicator. `find` and `search` are different tools: `find` is the
plain keyword search, no filters, answered instantly from the name index.
`search` is discovery with filters, and its keyword is optional.

    t.find('salariati')          plain keyword search, in name or code
    t.search('salariati', level='localitate')   keyword plus a filter
    t.search(level='localitate') filter alone, across the whole catalogue
    t.filters()                  which filters exist and what they accept
    t.domains()                  the 8 top level statistical domains
    t.overview()                 how big the catalogue is and where to start

`search` takes four filters, all optional, all combinable with each other and
with the keyword:

    level='judet'            territorial level
    caen=True                only those with a CAEN dimension
    domeniu='economic'       substring of the domain name, diacritics ignored
    periodicitate='lunar'    substring of the periodicity, diacritics ignored

    t.search(domeniu='economic', periodicitate='lunar', level='judet')

The substring filters are deliberately forgiving: `economic` matches
`B. STATISTICA ECONOMICA`, so you do not have to know the exact wording. Both
functions return every match; slice the result, or pass `limit=N`.

Understanding an indicator:

    m = t.matrix('FOM104D')      fetch the metadata
    m.what()                     what it measures: definition, unit, how often
    m.where()                    where it sits and what it covers
    m.how()                      its own download manual, ready to copy
    m.show()                     short summary: domain, levels, dimensions
    m.describe()                 the full record, every word INS wrote
    m.options()                  which dimensions it has, role and size
    m.options('teritoriu')       what values one dimension can take
    m.related()                  the other indicators under the same node

`show()` is the summary you read while browsing. `describe()` is the full
record, untruncated. Read it before you trust a series: FOM104D's observations
are where INS notes that 1990 is only available at county total level, and
definitions run to several thousand characters.

Fetching the data:

    df = m.get()                 the finest level it reaches, cleaned up
    m.get(level='judet')         one territorial level only
    m.get(levels=['judet', 'regiune'])   several levels
    m.get(level=None)            every level at once
    m.get(raw=True)              exactly what INS returned, no derived columns
    m.get(progress=True)         report progress on large indicators

## Levels and roles

Each dimension gets a role: `teritoriu`, `timp`, `caen`, `um` or `alt`. A
dimension counts as territorial if the `details` block says so, through
`nomJud`, `nomLoc` or `matRegJ`, or if its label mentions counties, localities,
regions or macroregions. Both routes matter: indicators built on the county plus
locality nomenclator are marked in `details`, but the common case is a single
hierarchical dimension holding macroregions, regions and counties together, and
there `details` is sometimes silent. CAEN works the same way, from either the
flags or the label.

`m.levels` lists the territorial levels present, from coarse to fine, out of
`national`, `macroregiune`, `regiune`, `judet`, `localitate` and `necunoscut`.
Levels come from the option labels: `TOTAL` and `Nivel National` are national,
`MACROREGIUNEA ...` is a macroregion, `REGIUNEA ...` is a region, and a county
is a name that appears in the actual list of Romanian counties.

Anything else is `necunoscut`, and that is deliberate. Territorial dimensions
also carry names that are not administrative units: air quality monitoring
stations, multi county groupings such as `Arges, Valcea`, `Extra-regiuni`,
`Nespecificat`. Calling those counties, which is what a catch all default does,
quietly corrupts any analysis that groups by county.

Naming a level the indicator does not have raises `ValueError`, lists the levels
it does have, and suggests the closest one:

    t.matrix("FOM101A").get(level="judete")
    ValueError: unknown level 'judete' for FOM101A. Available: national,
    macroregiune, regiune, judet. Did you mean 'judet'?

## The shape of the data

`m.get()` executes the indicator's fetch plan: it reads the strategy, runs it,
and applies tidy. Nothing is decided at request time. It returns a long format
DataFrame: one text column per dimension, in `dimensionsMap` order, a numeric
`Valoare` column, and the derived columns.

By default `get()` takes the finest territorial level the indicator actually
reaches, because a territorial dimension normally mixes the country total,
macroregions, regions and counties in one column and you rarely want them
stacked together. Indicators with no usable territorial level get no filter at
all and `get()` returns everything.

When county and locality are two separate dimensions, as in FOM104D, the level
picks which dimension is active and puts the other on its total:

    m.get(level="judet")        one row per county, localities on TOTAL
    m.get(level="localitate")   the localities, fetched county by county

The county dimension deliberately stays whole when localities are the active
one. The data is keyed by the real county and locality pair, so pinning the
county to its total returns nothing at all.

When the default leaves levels out, `get()` says so and names them:

    FOM106E: level judet (the finest), split:CAEN Rev.2 ..., 2 requests
      for every level, including national, macroregiune and regiune,
      use get(level=None)

`get(tidy=True)`, the default, adds derived columns and only adds: nothing is
dropped, renamed or reordered, and the original label keeps its SIRUTA prefix.
For every territorial dimension, using its label as the prefix:

    <label>_siruta    the SIRUTA code, Int64 nullable, NA for aggregates
    <label>_nivel     national, macroregiune, regiune, judet or localitate
    <label>_tip       municipiu, oras, comuna or sector, NA above locality
    <label>_nume      the name without the code and the type prefix

Only the columns that carry something are added. `<label>_nivel` is always
useful, so it is always there, but a county dimension gets nothing else:
counties have no SIRUTA code and no settlement type, and their name needs no
cleaning. FOM104D therefore ends up with `Judete_nivel` alone, and all four
columns for `Localitati`.

For every time dimension, `<label>_an` holds the year, as Int64.

The result is sparse. Combinations with no data are absent as whole rows, not
present as blanks, and this reflects real administrative history: Ilfov and
Municipiul Bucuresti do not appear before 1996. So do not validate a pull by
counting rows against the cartesian product of the dimensions, and do not assume
a complete grid when reshaping.

Column names come from `matrix.dimensions`, not from the CSV header. The API
replaces commas inside a dimension label with spaces, so the header arrives with
the comma gone. The parser checks the column count against the number of
dimensions plus one and raises if they disagree.

### Large indicators

A single POST is capped at `MAX_CELLS`, currently 100000 cells. Above that,
`get()` splits the work. Every indicator is downloadable; large ones just take
more requests.

Indicators that carry a locality dimension are downloaded one county at a time,
using `parentId`, which ties a locality to its county. Everything else is split
on its largest dimension, in pieces sized by how much room the other dimensions
leave, recursing when even a single option does not fit. The frames are
concatenated with `ignore_index=True`.

`progress="auto"`, the default, reports each request only when there is more
than one. Above 50 requests `get()` asks before starting; pass `confirm=False`
in scripts.

## Data wrangling

Frames from `get(tidy=True)` carry a `df.tempo` accessor, registered when you
import pytempo. It reshapes and summarizes, never fetches, and never changes
the frame you give it.

    df = t.get("FOM101A")

    df.tempo.coverage()
    #   Macroregiuni...judete  first_year  last_year  n_years  missing_years  min_value  min_year  max_value  max_year
    # 0                  Alba        1990       2024       35              0       92.1      2019      246.1      1990
    # 1                  Arad        1990       2024       35              0      123.1      2022      299.3      2011

    df.tempo.wide()
    #       Sexe  Macroregiuni...judete   1990   1991   1992
    # 0  Feminin                   Alba  116.5  113.0  114.5

`coverage()` is the first look at a series: one row per territorial unit, the
span of years it has, how many of the years seen anywhere in the frame are
missing for it, and the smallest and largest value with the year each occurred.
When the frame mixes territorial levels, the level comes first, so a national
total is never read as if it were a county.

`wide()` pivots time into columns. The index is built from the original
dimension columns, leaving out the derived ones, the original time column,
which says the same thing as the year, and a unit of measure column that never
varies.

`df.tempo.geo()` is a documented stub. It will join on SIRUTA and return a
GeoDataFrame, arriving as an optional `pytempo[geo]` extra so that anyone who
only wants the numbers never pays for the geometry stack.

Calling the accessor on a frame that is not tidy output says so plainly rather
than guessing.

## Loading into PostgreSQL

pytempo never connects to a database. It writes the SQL as text, and the
project downstream decides how to run it. That keeps the dependencies at
requests and pandas, and keeps the loading policy where it belongs.

The whole pipeline, on FOM101A:

    import pytempo as t
    from sqlalchemy import create_engine

    m = t.matrix("FOM101A")

    open("catalog.sql", "w").write(t.schema_catalog())   # shared tables
    open("fom101a.sql", "w").write(m.schema())           # one indicator

    # psql -f catalog.sql -f fom101a.sql

    df = m.get()
    df = df.rename(columns=t.column_mapping(m))
    engine = create_engine("postgresql://user@host/db")
    df.to_sql("fom101a", engine, schema="tempo", if_exists="append",
              index=False)

`m.schema()` generates `CREATE TABLE IF NOT EXISTS tempo.fom104d`, one text
column per dimension, a numeric value column, and exactly the derived columns
that `get(tidy=True)` produces for that indicator. Nothing is guessed twice:
the derived set is read from the standardization itself, so the table cannot
drift away from the DataFrame. A county dimension gets only its level column,
a locality dimension gets SIRUTA as `integer`, the type, the clean name and the
level, and time dimensions get the year as `smallint`. Indexes are generated on
SIRUTA and on the year where they exist.

`t.column_mapping(m)` gives the mapping from DataFrame column names to SQL
identifiers, so renaming is one line. Identifiers are folded to snake_case
without diacritics, truncated to fit Postgres, and made unique with a numeric
suffix on collision.

`t.schema_catalog()` generates the shared infrastructure: `indicators` and
`dimensions` describe the catalogue, and `territory` is a SIRUTA lookup keyed
by the code, which you fill from the data you extract. There are no hard
foreign keys pointing at the per indicator tables, because those may not exist
yet.

Both functions take `schema="..."` if you do not want the `tempo` schema, and
`m.schema(include_comments=False)` drops the `COMMENT ON` statements. The
comments carry the full INS name, the first sentence of the definition, and the
unit of measure, so the meaning travels with the table.

## Development

Install the library in editable mode, so your edits take effect without
reinstalling:

    pip install -e ".[dev]"

To use your working copy from another project while you develop, install it
editable into that project's own environment, pointing at your local path:

    pip install -e path/to/your/pytempo

In a notebook, reload edited modules without restarting the kernel:

    %load_ext autoreload
    %autoreload 2

## Internals: the schema registry

`pytempo/schemas/registry.json` is a census of the whole catalogue, one record
per indicator: its dimensions with their roles and sizes, levels, family, total
cell count, periodicity, domain, and whether it carries SIRUTA. It ships inside
the package and is versioned in the repo, so a fresh clone already has the map
and the metadata filters work immediately. Fetching the metadata is also the
endpoint test: `status` is `ok` only if the endpoint answered.

The file is written sorted and indented, so a change on the INS side shows up as
a readable git diff. It carries `registry_version`, and an unknown version
raises a clear error.

`family` decides how data gets fetched:

    judet_localitate    has a locality dimension, needs county by county
    teritorial_caen     territorial plus CAEN, no localities
    teritorial_simplu   territorial, no CAEN, no localities
    neteritorial        no territorial dimension at all
    alt                 anything else, listed individually in the report

Every `ok` entry also carries a `fetch_plan`, precomputed so that fetching is
execution rather than decision making: `default_level`, `strategy` (`single`,
`by_county` or `split:<dimension>`), `est_requests` and `tidy_ready`.

Nothing here is public API. Use it from a development shell:

    from pytempo import schemas

    schemas.build_registry()              # incremental: only codes not yet ok
    schemas.build_registry(refresh=True)  # rebuild everything, bypass the cache
    schemas.report()                      # reprint the census, no rebuild
    schemas.refresh_plans()               # recompute the plans, no network

`build_registry()` is incremental by default: it adds codes missing from the
registry and leaves the rest untouched. That means it does not notice an
indicator INS has changed, because it does not re-read its metadata. Use
`refresh=True` for that. After changing anything that affects classification,
rebuild and read the diff:

    git diff --stat pytempo/schemas/registry.json

### Validating against real data

The registry says what should happen. Validation asks for a small real slice of
each indicator, a few dozen cells in a single POST, and checks what came back:
the CSV parses, the column count matches, values are numeric, SIRUTA appears
where the entry claims it should, no negative counts of persons, and a cell
picked out of the slice returns the same value when requested on its own.

    schemas.validate(sample=15, seed=42)   # stratified sample, minutes
    schemas.validate()                     # the whole catalogue, hours
    schemas.validate()                     # again: resume skips what passed
    schemas.validate(codes=["POP214A"])    # targeted, to recheck after a fix

Sampling is stratified by family with a floor of three per family, so the small
families do not vanish behind the 71 percent that is `neteritorial`. Each
indicator gets `validated_at`, `validation` and `slice_cells` written back.
There are four outcomes:

    ok            every check passed
    empty         the slice came back with no rows, which is a legitimate answer
    error         a check we make failed, and that is worth investigating
    needs_review  the CSV itself could not be parsed

`needs_review` is deliberately not an error. Those are quirks of what INS sent,
each one a documented exception to read by hand, and the status carries the
likely cause. Two are known: EXP102A has a dimension whose label contains a
newline, so its CSV header spans two lines, and TEK0461 carries the
confidentiality marker `c` in the value column. Both also mean `get()` cannot
read those two indicators today.

Negative values are only flagged as implausible when the indicator is not a
balance. Names or dimension labels containing `spor`, `sold`, `migrat`,
`crestere`, `variatia` or `diferenta` are expected to go negative: POP214A
really does record a natural increase of -576 for Arges in 1995.

A separate survey looks at what the standardization actually produced, to tell
whether an oddity is isolated or a pattern:

    schemas.audit_standardization(sample=30)

It reports derived columns that would come out empty, territorial dimensions
whose levels are all `necunoscut`, and indicators where tidy adds nothing.

Finally, a list to check by hand:

    schemas.spot_check_list(5)

This is deliberately manual. The TEMPO site and the API are the same system, so
comparing them automatically would compare the API with itself and always agree.
A human reading the site is the only independent check, so the job here is to
hand them a ready made list of cells, each with the indicator URL.

## Contributing

    git clone https://github.com/CIDS-UBB/pytempo.git
    cd pytempo
    pip install -e ".[dev]"
    pytest -q
    python -m build

The tests run offline against fixtures, so they need no network.

Style rules:

* No em dash or en dash, anywhere: code, comments, docs.
* Comments and docstrings in English.
* Small modules with one job each. Do not inflate the structure.
* Every URL lives in `endpoints.py`. Do not hardcode one anywhere else.
* When you add a method, update `t.help()` and this README in the same commit.
* Document only what exists and works. Keep roadmap notes out of this file.

## Credits and prior work

pytempo learns from and credits earlier work on the same API.

The **R package TEMPO**, by Necula, Tiru and Oancea, is where the request
mechanics come from. Its chunking logic and endpoint paths are reimplemented in
Python here, including the insight that large matrices have to be fetched county
by county. It is described in:

* Necula, M., Tiru, A.M., Oancea, B. (2019). Tempo, an R package to access the
  TEMPO-Online database. *Romanian Statistical Review*, no. 3/2019.
* Tiru, A.M., Toma, I.E., Necula, M. (2017). The earlier rTempo package.
  *Romanian Statistical Review*, vol. 65, no. 4.

Code at [RProjectRomania/TEMPO](https://github.com/RProjectRomania/TEMPO).

The shape of the Python API was informed by
[tempo.py](https://github.com/mark-veres/tempo.py), and
[gov2-ro/tempo-ins-dump](https://github.com/gov2-ro/tempo-ins-dump) served as a
validation reference.

What is original here: the role and level classification derived from the
`details` block with label fallbacks, the schema registry with precomputed fetch
plans, the standardization that adds SIRUTA as a key without touching the
original labels, and the validation harness that checks slices of real data
against the registry.

## License

MIT.
