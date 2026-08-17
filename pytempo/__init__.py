"""pytempo: simple access to the INS TEMPO Online data.

Start with t.help(), which lists what the package can do. Discovery (find,
search, domains, overview), understanding (matrix, what, where, how, info,
show, describe, options) and fetching the data (get for the usual case,
download for the large ones, which go through disk with a checkpoint).
"""
from .catalog import (build_index, domains, filters, find, load_index,
                      name_dict, overview, search)
from .matrix import Matrix, MatrixList, download, get, info, matrix
from .schema import catalog_ddl as schema_catalog
from .schema import column_mapping
from . import wrangle  # noqa: F401  registers the df.tempo accessor

# explore.init and explore.browse are sketches that still raise
# NotImplementedError, so they are deliberately not exported yet

__version__ = "0.25.0"
__all__ = [
    "load_index", "name_dict", "search", "find", "domains", "overview",
    "build_index", "filters",
    "matrix", "info", "get", "download",
    "Matrix", "MatrixList",
    "schema_catalog", "column_mapping",
    "help",
    "__version__",
]


def help() -> None:
    """A navigation guide: what the package can do, grouped by intent."""
    print("""pytempo, a navigation guide. Import it with: import pytempo as t

FIND an indicator
  t.find('salariati')          plain keyword search, instant
  t.search('salariati', level='localitate')   discovery with filters
  t.search(level='localitate') filters work with no keyword, across everything
  t.filters()                  which filters search has and what they accept
  t.build_index()              the metadata index, once, a few minutes
  t.domains()                  the 8 top level statistical domains
  t.overview()                 how big the catalogue is and where to start

DISCOVERY FILTERS, all optional and combinable
  level='judet'                territorial level
  caen=True                    only those with a CAEN dimension (False the rest)
  domeniu='economic'           substring of the domain name
  periodicitate='lunar'        substring of the periodicity
  t.search(domeniu='economic', periodicitate='lunar', level='judet')

UNDERSTAND an indicator
  m = t.matrix('FOM104D')      fetch the metadata
  m.what()                     what it measures: definition, unit, how often
  m.where()                    where it sits and what it covers
  m.how()                      its own download manual, ready to copy
  m.show()                     short summary: domain, levels, dimensions
  m.describe()                 the full record, every word INS wrote
  m.options()                  which dimensions it has, with role and size
  t.info('FOM104D')            the same metadata, as a dictionary
  m.related()                  the other indicators under the same node
  m.levels                     levels, e.g. ['national', 'judet', 'localitate']
  m.has_siruta                 True if localities carry a SIRUTA prefix
  m.options('teritoriu')       what values one dimension takes
  m.options('varsta', kind='groups')   just the aggregates of a hierarchy
  m.locality_dimension         which dimension holds the localities, or None
  m.territory_columns()        the columns of the fine territory, by content
  m.help()                     this guide, for one indicator

FETCH the data
  df = m.get()                 the finest level, tidied, with progress
  m.get(level='judet')         one territorial level only
  m.get(levels=['judet','regiune'])   several levels
  m.get(level=None)            every level at once, the old default
  m.get(select={'Sexe': ['Masculin']})   keep only some options of a dimension
  m.get(select={'varsta': 'groups'})     or a kind: groups, leaves, total
  m.get(raw=True)              exactly what INS returns, no derived columns
  t.get('FOM101A')             the same, starting from a code
  m.download(folder='data/x')  for the large ones, see the next section
  t.download('POP107D', folder='data/pop107d')   the same, from a code
  m.how()                      says which of the two this indicator needs

FETCH a large one, through disk
  df = m.download(folder='data/san101b')   each request written as it arrives
  m.download(folder=..., return_df=False)  the CSV path, nothing held in memory
  t.download('SAN101B', folder=...)        the same, starting from a code

Which of the two: get() for anything that fits in memory, which is almost every
indicator, and download() past 50 requests, where get() stops and says so.
m.how() prints the answer for one indicator, with the command to copy.

download() takes the same level, levels and select as get() and builds the same
plan. What changes is that every request is written to its own slice file the
moment it comes back, so memory stays at one request and nothing is lost if the
server drops out. Rerun the same call and resume=True asks only for the slices
that are not on disk yet. At the end the slices become one CSV and are removed.

The joining is then checked, automatically, and anything odd is printed rather
than left in the file: slices that never arrived, rows lost or doubled on the
join, a combination of dimensions that occurs twice, a select that came back
with more or fewer distinct values than were asked for. The frame carries the
verdict as df.attrs['complete'] and df.attrs['aggregation_warnings'].

RESHAPE it, on any frame from get(tidy=True)
  df.tempo.coverage()          per unit: span of years, holes, extremes
  df.tempo.wide()              pivot time into columns, one per year
  df.tempo.spot_check(2)       two random units, ready to check on the site
  df.tempo.geo()               join on SIRUTA, not implemented yet

spot_check() prepares the one check nothing internal can do: reading the same
number off TEMPO Online. It picks units at random, pins every other dimension
on its total so the site shows a single series, says what it pinned, and prints
the series year by year. seed= makes the choice reproducible. It touches no
network, only the frame you already have.

LOAD it into PostgreSQL, pytempo writes the SQL, you run it
  m.schema()                   CREATE TABLE for this indicator, as text
  t.schema_catalog()           the shared indicators, dimensions and territory
  t.column_mapping(m)          DataFrame names to SQL names, for df.rename

get() executes the plan from the registry: it reads the strategy, runs it and
applies tidy. By default it takes the finest level the indicator reaches and
says in one line what it decided. Indicators with no usable level get
everything.

select= trims a dimension before the query is built, so nothing you did not ask
for is downloaded. Its key is a dimension label, exactly or as a unique
substring; its value is a list of nomItemIds, a list of option labels, or a
predicate on the option, for instance select={'Ani': lambda o: '202' in o.label}.
Dimensions it does not name stay whole, and level= then works on what is left.

A value can also be a kind, for a dimension that has levels inside it:
'groups', or 'parents', keeps the aggregates, 'leaves' keeps the finest level,
'total' keeps the total. select={'varsta': 'groups'} on POP107D is the 19 age
groups instead of the 104 options, without a loop over the labels and without
knowing how INS writes them. m.options('varsta', kind='groups') shows the same
19 before you download anything. A dimension with no levels inside it, and
plenty have none, says so rather than guessing.

When county and locality are two separate dimensions, as in FOM104D, a level
picks which one is active and puts the other on its total: level='judet' gives
one row per county in a single request, level='localitate' gives the
localities, county by county.

Every dimension carries a role, teritoriu, timp, caen, um or alt, and a
territorial one also carries finest_level, the finest level it reaches. That is
how to tell a county dimension from a locality one without reading its name,
which is not a reliable guide: FOM104D calls the localities 'Localitati' and
GOS102A calls them 'Municipii si orase'. The columns keep those names, the
library renames nothing; m.locality_dimension and m.territory_columns() are how
you find them without hardcoding either spelling.

The data is sparse, and deliberately so: INS writes ':' when it has no figure
and '0' when it measured a zero, which are different statements. pytempo keeps
them apart. A ':' arrives as no row at all, so the combination is absent from
the result; a '0' arrives as a row whose Valoare is 0.0. Never read an absent
year or an absent locality as a zero, and do not assume a complete grid when
joining or averaging: what to do with what is missing is your decision to make,
and df.tempo.coverage() shows where the holes are.

Indicators that do not fit one POST are downloaded in several requests
and concatenated: county by county for those with localities, otherwise split on
the largest dimension. Above 50 requests get() stops and points at download(),
which checkpoints on disk; get(confirm=False) goes ahead in memory anyway. tidy
never drops or reorders anything: the original name stays, SIRUTA prefix and
all.

The POST to pivot retries by itself: a read timeout, a dropped connection or a
5xx is sent again up to three times, with growing waits. In download() a slice
that still fails is reported and skipped, so one bad request does not undo the
ones that worked.

find and search are different tools. find is the fast keyword search, without
filters. search is discovery with filters, and works with no keyword at all.
Both return EVERY match; slice them, or pass limit=N.

The metadata filters resolve from the local registry, so they are instant. The
registry ships with the package, so nothing needs building first.

Lists returned by find, domains and related render as a table and carry
.recent(n), which orders by last update date within that set only. The table
also shows a levels column, but only when every element already knows its
levels, which is the case for filtered search results. Display never costs a
network call.""")
