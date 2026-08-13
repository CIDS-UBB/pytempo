"""pytempo: simple access to the INS TEMPO Online data.

Start with t.help(), which lists what the package can do. Discovery (find,
search, domains, overview), understanding (matrix, what, where, how, info,
show, describe, options) and fetching the data (get).
"""
from .catalog import (build_index, domains, filters, find, load_index,
                      name_dict, overview, search)
from .matrix import Matrix, MatrixList, get, info, matrix
from .explore import init, browse

__version__ = "0.15.2"
__all__ = [
    "load_index", "name_dict", "search", "find", "domains", "overview",
    "build_index", "filters",
    "matrix", "info", "get",
    "Matrix", "MatrixList",
    "init", "browse",
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
  m.help()                     this guide, for one indicator

FETCH the data
  df = m.get()                 the finest level, tidied, with progress
  m.get(level='judet')         one territorial level only
  m.get(levels=['judet','regiune'])   several levels
  m.get(level=None)            every level at once, the old default
  m.get(raw=True)              exactly what INS returns, no derived columns
  t.get('FOM101A')             the same, starting from a code

get() executes the plan from the registry: it reads the strategy, runs it and
applies tidy. By default it takes the finest level the indicator reaches and
says in one line what it decided. Indicators with no usable level get
everything.

The data is sparse: combinations with no data are absent as whole rows, not as
blanks. Indicators that do not fit one POST are downloaded in several requests
and concatenated: county by county for those with localities, otherwise split on
the largest dimension. Above 50 requests get() asks first; pass confirm=False in
scripts. tidy never drops or reorders anything: the original name stays, SIRUTA
prefix and all.

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
