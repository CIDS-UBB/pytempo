# pytempo

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.30.0-informational.svg)](pyproject.toml)

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
    m.how()                              # its own menu, ready to copy

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

There are two scripts next to them: `examples/quickstart.py`, the same ground in
one runnable file, and `examples/check_links.py`, which confirms the live
endpoints answer.

## What it does

* **Finds indicators.** 1916 of them, searchable by keyword, or filtered by
  territorial level, domain, periodicity and whether they carry a CAEN
  classification.
* **Reads the metadata.** Definitions, methodology, sources and observations
  exactly as INS wrote them, plus the dimensions with their roles and sizes.
* **Fetches the data at any level.** From national totals down to localities,
  splitting large requests automatically so every indicator is downloadable.
  The big ones go through disk with `download()`, which checkpoints each
  request and resumes where it stopped.
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
    m.how()                      its own menu: the call, the levels, the filters
    m.show()                     short summary: domain, levels, dimensions
    m.describe()                 the full record, every word INS wrote
    m.options()                  which dimensions it has, role and size
    m.options('teritoriu')       what values one dimension can take
    m.options('varsta', kind='groups')   just the aggregates of a hierarchy
    m.locality_dimension         which dimension holds the localities, or None
    m.territory_columns()        the columns of the fine territory, by content
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
    m.get(select={'Sexe': ['Masculin']})  only some options of a dimension
    m.get(select={'varsta': 'groups'})   or a kind: groups, leaves, total
    m.get(raw=True)              exactly what INS returned, no derived columns
    m.get(progress=True)         report progress on large indicators
    m.download(folder='data/x')  large ones: through disk, resumable

### get or download

Two ways to pull an indicator, and the choice is not a preference:

    m.get()                      holds the whole thing in memory
    m.download(folder='data/x')  writes each request to disk as it arrives

`get()` is right for almost every indicator: one request, or a handful, and a
frame at the end. Past 50 requests it stops and refuses, because keeping a
hundred requests in memory and losing all of them to one late timeout is not a
download, it is a gamble. That is where `download()` belongs: same arguments,
same plan, but each slice is written as it comes back, a broken run resumes
where it stopped, and a request that times out is retried rather than fatal.

You do not have to guess which one an indicator needs. `m.how()` says so, and
the rest of the menu with it, in the section below.

If `get()` does stop you, it says the same thing, for that indicator, and it
says it as guidance rather than as a crash:

    POP107D IS TOO LARGE FOR get(). Nothing has been downloaded.
      380 requests, over the 50 get() will hold in memory. get() keeps
      every one of them until the last comes back, so a single late timeout,
      and INS does time out, loses all of it with nothing to resume from.

      Use download() instead, which is the same call through disk:
        m.download(folder='data/pop107d')
      It writes each request as it arrives, resumes where it stopped, and
      retries on timeout.

      m.how()                the whole menu for POP107D: every level, every filter
      m.get(confirm=False)   go ahead with get() anyway, in memory, no checkpoint

    MatrixTooLargeError: POP107D: 380 requests, use download(). See the
    guidance above, or m.how().

That layout is deliberate. The guidance is printed, and the exception that
follows carries a single line, because in a notebook a paragraph inside an
exception comes out under `Traceback (most recent call last)`, with a file and
a line number, and being told what to do next should not look like something
breaking.

It does still stop, and that is not cosmetic: returning nothing quietly would
let a script carry on with data it never got and fail somewhere further away,
where the reason is no longer in sight. `MatrixTooLargeError` is a subclass of
`ValueError`, so anything already catching one keeps working, and you can catch
it by name when you want to handle the case yourself:

    try:
        df = m.get()
    except t.MatrixTooLargeError:
        df = m.download(folder='data/pop107d')

The full description of `download()`, its arguments and its checks, is further
down, under Large indicators.

### how: the menu of one indicator

`how()` is where to start on an indicator you do not know. It reads the
dimensions it actually has and prints what you can choose, with the call
already written. TUR101B, tourist accommodation, has no territory and three
things to filter:

    t.matrix("TUR101B").how()

    How to download TUR101B
      Structuri de primire turistica cu functiuni de cazare turistica pe
      tipuri de structuri, categorii de confort si destinatii turistice

      THE CALL, ready to copy:
        m.get(select={'tipuri': 'groups', 'categorii': 'total', 'destinatii': 'total'})
        1 request

        Why this shape: 'groups' on tipuri keeps the 17 aggregates and leaves
        out the finer breakdown under them, and 'total' on categorii and
        destinatii, since a breakdown you did not ask for multiplies the rows
        without adding an answer. Change any of it below.

      NO TERRITORIAL LEVEL: this indicator is not territorial,
      so level= does not apply and get() takes every option.

      FILTERS, all optional. The short name on the left is what you write:

        tipuri      Tipuri de structuri de primire turistica
                    19 options on 2 levels
                    'groups'   17: Total, Hoteluri, Hoteluri pentru tineret, ...
                    'leaves'    2: Pensiuni turistice, Pensiuni agroturistice
                    'total'     1: Total

        categorii   Categorii de confort
                    19 options, one level
                    values: Total, 5 stele, 4 stele, ...
                    a few:  select={'categorii': ['5 stele']}
                    or one: select={'categorii': 'total'}

        destinatii  Destinatii turistice
                    7 options, one level
                    values: Total, Statiuni balneare, Statiuni din zona litorala..., ...
                    a few:  select={'destinatii': ['Statiuni balneare']}
                    or one: select={'destinatii': 'total'}

      m.options('tipuri')   every option of one of them, in full
      m.get(raw=True)       exactly what INS returns, no extras
      m.how(full=True)      the plan, the strategy, the rest

Four things about that page are deliberate.

**The call comes first**, with the reason for its shape written out. The
default is every option of every dimension, and on an indicator with three of
them that is a cross tabulation nobody asked for. So the suggestion varies one
dimension, the largest hierarchy, and puts the rest on their total.

**Each name is written once.** `Tipuri de structuri de primire turistica` used
to appear four times, once per select line. It appears once, and everything
after it uses `tipuri`, which is a name you can type. `select=` has always
accepted any part of a label that names one dimension and no other, so the
short name was already there; it was simply never shown. Each one printed is
checked through the same resolver `select=` uses, so it always lands on the
dimension it was printed for, and a label with nothing unambiguously short
about it keeps its full name.

**Counts come with values.** `17 options` says nothing about what they are;
`17: Total, Hoteluri, Hoteluri pentru tineret, ...` does. It also makes an odd
classification visible: the two `leaves` above are `Pensiuni turistice` and
`Pensiuni agroturistice`, which is INS indenting two of nineteen types for
reasons of its own, and now you can see that before you download rather than
after.

**The mechanics are one line away**, not in your way. `m.how(full=True)` adds
the strategy, the request count of the default call, the raw form and the note
on indicators that keep county and locality apart.

On a territorial indicator the levels are a menu of their own, one to pick,
with what each one costs:

      TERRITORIAL LEVEL, pick one:
        national          1 unit,     1 request   m.get(level='national')
        judet           42 units,     5 requests  m.get(level='judet')
        localitate    3181 units,   379 requests  m.download(level='localitate', folder='data/pop107d')   default, the finest
        every level at once                       m.get(level=None)

Every number is read off that indicator, not off a template. The units per
level are counted from the options; the requests per level are counted by
planning that exact download, which is how `how()` knows to offer
`get(level='judet')` and `download(level='localitate')` in the same table; the
option counts of each keyword come from the same hierarchy detection `select=`
uses. The suggested call is planned too, filter included, which is why on
POP107D it says 42 requests rather than the 380 the indicator costs whole: the
filter is what makes it reachable.

An indicator with nothing but territory and time says so, rather than showing
an empty section:

    FILTERS: none to add. This indicator is territory and time only,
    so the level above is the whole choice.

## Levels and roles

Each dimension gets a role: `teritoriu`, `timp`, `caen`, `um` or `alt`. A
dimension counts as territorial if the `details` block says so, through
`nomJud`, `nomLoc` or `matRegJ`, or if its label mentions counties, localities,
regions or macroregions. Both routes matter: indicators built on the county plus
locality nomenclator are marked in `details`, but the common case is a single
hierarchical dimension holding macroregions, regions and counties together, and
there `details` is sometimes silent. A third route, described below, reads the
options themselves when neither of the first two says anything. CAEN works the
same way, from either the flags or the label.

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

### Finding the fine territory

`teritoriu` covers both a county dimension and a locality one, so a territorial
dimension also carries `finest_level`, the finest real level it reaches. That
is the sub sign that tells them apart, and it is what `m.options()` shows:

    m.options()
    [0] Judete (teritoriu/judet, 43 options)
    [1] Municipii si orase (teritoriu/localitate, 321 options)
    [2] Ani (timp, 32 options)
    [3] UM: Ha (um, 1 options)

That indicator is GOS102A, and it is the reason this exists: its locality
dimension is called `Municipii si orase`, not `Localitati`. The download is
correct either way, and the derived columns come out under that name, prefix
and all, because the library never renames anything INS wrote. What breaks is
downstream code that looks for the literal `Localitati_siruta`: it finds
nothing, says nothing, and writes a file with no SIRUTA and no locality name.

So ask, rather than guess:

    m = t.matrix('GOS102A')

    m.locality_dimension.label      # 'Municipii si orase', or None if there is
                                    # no locality dimension at all
    m.territory_columns()
    {'label': 'Municipii si orase',
     'siruta': 'Municipii si orase_siruta',
     'nivel': 'Municipii si orase_nivel',
     'tip': 'Municipii si orase_tip',
     'nume': 'Municipii si orase_nume'}

`label` is the original column, carrying the INS name; the rest are the derived
ones, keyed by what they hold. Downstream maps from that, never from a spelling:

    columns = m.territory_columns()
    df = m.get(level='localitate').rename(columns={
        columns['siruta']: 'siruta', columns['nume']: 'uat_name'})

`territory_columns()` names the columns of the finest territorial dimension,
which is the locality one when there is one and the county one otherwise, so
an indicator that stops at counties gives `label` and `nivel` and no `siruta`
key, rather than a name for a column that will not be there. An indicator with
no territorial dimension gives an empty dict. Neither is an error.

A dimension is territorial when `details` says so, when its label says so, or,
as a last resort, when its options themselves name places: a settlement type
such as `MUNICIPIUL` or a name from the county nomenclator. A numeric prefix
alone is not evidence, since `0 ani` starts with a number exactly the way
`1017 MUNICIPIUL ALBA IULIA` does.

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

### Missing is not zero

INS makes a distinction that most exports lose. On the site, `:` means it has no
figure for that combination, and `0` means it measured a zero. Those are
different statements: a commune with no births registered in a year is not the
same as a commune whose figure was never published.

pytempo keeps them apart, in the only way that keeps them apart honestly:

* a `:` arrives as **no row at all**, so the combination is simply not in the
  frame;
* a `0` arrives as a **row whose `Valoare` is `0.0`**.

A small commune therefore looks like this, and both facts are visible:

    df[df["Localitati_siruta"] == 2130][["Ani_an", "Valoare"]]
       Ani_an  Valoare
    12   2019      3.0
    13   2021      0.0      # a measured zero: nothing happened that year
    14   2022      1.0
                            # 2020 is not here at all: INS published ':'

The consequence is yours to handle, and it is a decision, not a detail. Before
you join on year, compute a rate, or average a series, choose what an absent
year means for your question: filling it with zero states that nothing happened,
which is a claim INS did not make. `df.tempo.coverage()` reports, per unit,
which years are there and how many are missing, so the holes are visible before
they turn into numbers.

Column names come from `matrix.dimensions`, not from the CSV header. The API
replaces commas inside a dimension label with spaces, so the header arrives with
the comma gone. The parser checks the column count against the number of
dimensions plus one and raises if they disagree.

### Choosing options with select

`get()` sends every option of every dimension it was not told to trim, which is
right for a first look and wasteful once you know what you want: POP107D has 104
age groups, and asking for two of them used to cost all 104. `select=` names a
dimension and says which of its options to keep:

    m = t.matrix('POP107D')
    m.options()                       # which dimensions it has
    m.options('Varste si grupe de varsta')     # and what they can take

    df = m.get(level='judet',
               select={'varsta': ['0- 4 ani', '5- 9 ani'], 'Sexe': 'Masculin'})

    POP107D: level judet, single, 1 request
      select: Varste si grupe de varsta limited to 2 of 104 options
      select: Sexe limited to 1 of 3 options

    df.shape                          # (2940, 10), two age groups, 42 counties

The key is a dimension label, matched exactly first, ignoring case and
surrounding space, then as a unique substring, so `varsta` finds
`Varste si grupe de varsta` and `tipuri` finds
`Tipuri de structuri de primire turistica`. An ambiguous key is an error that
lists the candidates rather than a guess. `how()` prints the short name of each
dimension, so you do not have to invent one.

The value takes four forms: a list of `nomItemId` numbers, a list of option
labels, a predicate on the option, for instance
`select={'Ani': lambda o: '202' in o.label}`, or one of the words below. A
single value stands for a list of one. Whatever the form, a name that matches
nothing is named in the error, with a suggestion when one is close.

### Selecting a kind of option

Many dimensions have levels inside them. POP107D's 104 ages are 19 groups,
`Total` and eighteen five year bands, and the 85 single ages under them. Asking
for the groups used to mean a loop over the labels, keeping the ones with a
hyphen or the one that says `Total`, which is a guess about how INS writes
names and breaks on the next dimension.

`select` takes a word instead:

    m.options('varsta', kind='groups')   # see the 19 first
    Total,    0- 4 ani,    5- 9 ani,    10-14 ani, ...,    85 ani si peste

    m.download(level='localitate', folder='data/pop107d',
               select={'varsta': 'groups'})

    groups   the aggregates: every level above the finest one, plus the total
    parents  the same thing, if that word reads better where you are
    leaves   the finest level, without the total
    total    the total alone

They are not about ages. On AGR101A, land use, `groups` gives `Total`,
`Agricola`, `Terenuri neagricole total` and `Alte suprafete`, and `leaves`
gives the ten kinds of land under them. Any dimension with levels answers.

**Where the levels come from.** Measured across the catalogue before any of
this was written: `parentId` is populated only on locality dimensions, where it
points at the county, that is at an option of another dimension. It is null on
POP107D and POP105A ages, on FOM104F's CAEN, on SCL101B's levels of education,
on AGR101A's land use, and even on hierarchical territory. `offset` is a plain
running order. What INS does carry is the indentation of the label, three
spaces per level, which is what it renders its own tree from:

    'Total'
    '   0- 4 ani'
    '      0 ani'

So `parentId` is read first, because it is explicit wherever it exists, and the
indentation second, because it is what the live catalogue actually has. The
indentation is a layout signal rather than a naming pattern: it says nothing
about what an option is called, only about where it sits, which is why it works
on dimensions this library has never seen. It is still a fallback, and if INS
stopped indenting, the words would report a flat dimension rather than guess.

**A kind is a level, not a count of children.** `85 ani si peste` has no single
ages under it, since INS does not list ages past 85 one by one, and
`Alte suprafete` has nothing under it either. Calling an option a group only
when something sits beneath it would drop the first from the age groups and the
second from land use, leaving a set of aggregates that does not add up to its
own total. Both are written at the level of the aggregates, and that is what
they are.

A dimension with no levels inside it, and plenty have none, says so:

    m.get(select={'Niveluri de educatie': 'groups'})
    ValueError: select 'groups' on 'Niveluri de educatie': this dimension is
    not hierarchical, its 18 options are all at the same level, so there are no
    groups to keep and no leaves to drop. Name the options you want, as labels
    or as nomItemIds, or pass a predicate.

Dimensions `select` does not name stay whole, and everything downstream works on
the smaller set: the cell count, the chunking strategy, the query and the tidy
columns. `select` and `level` compose in that order, `select` first: choosing
three counties and asking for `level='judet'` gives those three, not all of
them. `how()` is unaffected, since it describes the whole indicator; `select` is
an override for one call.

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
than one. Above 50 requests `get()` stops and sends you to `download()`, which
is the subject of the next section; `get(confirm=False)` goes ahead in memory
anyway.

### download: through disk, with a checkpoint

`get()` holds every frame in memory until the last request comes back. That is
right for almost every indicator and wrong for the few big ones. SAN101B, 36
categories by 3 properties by 3177 localities by 31 years, is a plan of 130
requests: through `get()` it ran for five hours and was abandoned, while
writing each county to disk as it arrived took under three minutes. The cost is
not the concatenation, which happens once at the end. It is that nothing is
saved until everything is done, so a single late failure loses all of it and
there is nothing to resume from.

`download()` takes the same `level`, `levels` and `select` as `get()` and
builds the same plan through the same code. What changes is where the answers
go: each request is written to its own slice file the moment it arrives.

    m = t.matrix('SAN101B')
    df = m.download(folder='data/san101b')

    SAN101B: level localitate, by_county, 130 requests
      slices as parquet in data/san101b
      1/130: +2418 rows -> _chunk_0001_9f3c1ad2.parquet
      2/130: +1932 rows -> _chunk_0002_44be07e1.parquet
      ...
      271914 rows from 130 of 130 requests -> data/san101b/SAN101B.csv

Memory stays at one request, and an interrupted run keeps what it had. Run the
same call again and `resume=True`, the default, skips every request whose slice
is already on disk, so only what is missing goes over the wire. A slice is
named after the index of the request and a hash of its `encQuery`, so a resume
can never hand back a slice that answers a different question.

A request that still fails after the client has finished retrying is written
down and skipped, never raised: one bad request out of a hundred must not undo
the ninety nine that worked. What is missing is reported at the end, the slices
are kept so the next run continues from them, and the frame carries the list in
`df.attrs['missing_requests']`.

    folder=None        work in a temporary folder and clean it up afterwards
    out='x.csv'        the path of the consolidated CSV, default <code>.csv
    return_df=False    return that path instead of the frame, holding nothing
    resume=False       ask for everything again, ignoring what is on disk
    tidy, raw          exactly as in get()

When the slices are consolidated they become one CSV, `;` separated and
`utf-8-sig` encoded, and are then removed. With `return_df=False` the CSV is
written slice by slice, so an indicator too large to fit in memory still ends
up as one file.

Slices are Parquet when `pyarrow` is installed, which is faster and keeps the
dtypes, and CSV otherwise, which is the same mechanism in another format. The
core stays on `requests` and `pandas` alone, so Parquet is an optional extra:

    pip install "pytempo-ins[fast]"

### What download checks before it hands the data over

A download of a hundred requests fails in ways a single request cannot, and
none of them raise: a slice that never arrived, a piece counted twice, a filter
that did not reach the query. The result still looks like a finished file. So
every `download()` ends with a check on the joining, automatically, and says
what it found:

    aggregation check: 271914 rows, complete, no duplicates

Four things are checked:

* **Completeness.** How many slices are on disk against how many the plan asked
  for. If any are absent the result is marked `INCOMPLETE` and the failed
  requests are named, so nothing pretends to be the whole indicator.
* **Row conservation.** The rows of the joined frame against the sum of the
  rows of every slice. A difference means something was lost or doubled while
  joining.
* **Duplicate keys.** No combination of the dimension columns, everything that
  is not `Valoare`, may occur twice.
* **The filter.** When `select` was given, each filtered dimension must come
  back with exactly as many distinct values as were selected. More means the
  filter never reached the query; fewer means it cut too deep, or that INS has
  no data for the rest, which is said as a possibility rather than assumed.

Warnings are printed even with `progress=False`: silence about progress is a
preference, silence about a frame that is wrong is not. The same verdict
travels with the data, in `df.attrs['complete']`,
`df.attrs['aggregation_warnings']` and `df.attrs['missing_requests']`, so a
script can check without reading the printout. With `return_df=False` there is
no frame to inspect, and the two checks that need one say so instead of passing
by default.

### When the server does not answer

The POST to pivot retries by itself. A read timeout, a dropped connection or a
5xx is the INS server having a bad moment, so the request goes out again after
a growing wait: up to three attempts, 5 then 15 seconds apart. The per request
timeout is 60 seconds, not 30, because a heavy request on a slow day needs it.
A 4xx is our own bad query and surfaces at once, since retrying it would only
be slower. When every attempt fails the error says it is the server and to try
again later, and in `download()` that failure costs one slice, not the whole
run.

### Rate limiting, and what it looks like

There is a third way for the server to be unwell, and on a long download it is
the usual one: `pivot` answers `200` with an **empty body**, zero bytes.
Measured on POP108D, 83 slices: the first 42 came back with data in seconds,
and then every single one of the remaining 41 was empty. Nothing was wrong with
those requests. INS had simply had enough.

That is not the same as a combination with no data, which comes back as a CSV
with a header and no rows and is perfectly legitimate. The two are spelled
differently, which is what makes the empty one safe to retry: waiting for a
zero byte answer never throws away a real empty result.

So an empty body is retried like a timeout, on the same growing waits, and it
usually clears. If it does not clear, it is reported as a failed slice rather
than accepted as no data: writing a hole into the file would be reading a
missing figure as a zero, which pytempo does not do anywhere else either.
`resume=True` then finishes the job on the next run, asking only for the slices
that are still missing.

The other half of the answer is not to provoke it. `download()` leaves a gap
between one request and the next, half a second by default, which costs under a
minute on a download of a hundred and keeps the server willing. When slices
start failing anyway the gap doubles, up to eight seconds: INS has had enough,
and knocking harder is not an argument. For a small download where politeness
costs more than it buys:

    import pytempo
    pytempo.incremental.REQUEST_SPACING = 0

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

    df.tempo.spot_check(2, seed=7)      # two random units, to check by hand

`coverage()` is the first look at a series: one row per territorial unit, the
span of years it has, how many of the years seen anywhere in the frame are
missing for it, and the smallest and largest value with the year each occurred.
When the frame mixes territorial levels, the level comes first, so a national
total is never read as if it were a county.

Units are keyed by SIRUTA, never by name. Locality names are not unique in
Romania: ALBAC exists in Alba and in Cluj, and they are different places.
Grouping by name would merge them into one row with a minimum from one county
and a maximum from the other. The name and, where a second territorial
dimension exists, the county are shown as labels, so homonyms are also easy to
tell apart by eye.

`wide()` pivots time into columns. The index is built from the original
dimension columns, leaving out the derived ones, the original time column,
which says the same thing as the year, and a unit of measure column that never
varies.

`df.tempo.geo()` is a documented stub. It will join on SIRUTA and return a
GeoDataFrame, arriving as an optional `pytempo[geo]` extra so that anyone who
only wants the numbers never pays for the geometry stack.

Calling the accessor on a frame that is not tidy output says so plainly rather
than guessing.

### Checking a download by hand

Every check inside the library is a check on itself. The one error none of them
can catch is a number that is correct and means something else: the wrong
option pinned, the wrong dimension read, a series that is not the one you
thought you asked for. The only thing that catches that is opening TEMPO Online
and reading the same number off the site.

What makes that tedious is the setup, not the comparison: finding one locality
among three thousand, and working out which option every other dimension has to
be on for the site to show a single line. `spot_check()` does the setup:

    df.tempo.spot_check(2, seed=7)

    spot check: 2 of 3182 units, seed 7
      1. 2130 ALBAC  [Judete: Alba]  siruta 2130
         fixed Varste si grupe de varsta = Total
         fixed Sexe = Total
         3 years:
           2020  1834.0
           2021  1802.0
           2022  1795.0
      2. 1017 MUNICIPIUL ALBA IULIA  [Judete: Alba]  siruta 1017
         ...
      read the same numbers at http://statistici.insse.ro:8077/tempo-online/
      open the same indicator, pick the same options, compare year by year
      a year missing here is a ':' on the site, not a zero

It picks `n` units at random from those that carry a value, names each one with
its county and its SIRUTA, pins every other dimension on its total so the site
shows a single series, and prints that series year by year. A dimension with no
total gets its first option and is named as such, because a pinned dimension
the reader does not know about is how a spot check ends up comparing two
different things.

`seed=` makes the choice reproducible, so a spot check can live in a script and
be rerun after a change. Nothing here touches the network: it reads the frame
you already downloaded and prints. Where to go with it is the only thing it
knows about the site.

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

The tests run offline, on fixtures, with `client.post_pivot` mocked. One of
them runs at scale: `tests/fixtures/POP107D_meta.json` is the real answer of
`matrix/POP107D`, saved once, with its 104 ages, 43 counties and 3182
localities. Loaded from the file it gives a plan of dozens of requests, split
county by county, so the joining is exercised on the shape that actually
breaks, and the same data asked for in one request and in fifty is compared
frame to frame.

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
