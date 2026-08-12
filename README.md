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
    t.search("someri", limit=5)   # the same thing, longer name
    t.domains()                   # the 8 top level statistical domains

    m = t.matrix("FOM104D")       # fetch one indicator's metadata
    m.show()                      # readable summary
    m.levels                      # ['judet', 'localitate']
    m.has_siruta                  # True when locality labels carry a SIRUTA prefix
    m.where()                     # A. STATISTICA SOCIALA > FORTA DE MUNCA > SALARIATI
    m.related()                   # the other indicators under the same node
    m.options("Judete")           # what values that dimension can take

    t.info("FOM104D")             # the same metadata as a plain dict
    t.load_index()                # every indicator: [{code, name}, ...]
    t.name_dict()                 # {code: name}

Search matches all the words you give it, in the name or the code, case
insensitively and ignoring Romanian diacritics, so `someri` finds `Șomerii`.

A quick check that the live endpoints answer:

    python examples/check_links.py

## Navigating

Finding an indicator:

    t.find('salariati')          search by keyword, in name or code
    t.search('someri', limit=5)  the same thing, longer name
    t.domains()                  the 8 top level statistical domains
    t.overview()                 how big the catalogue is and where to start

Understanding an indicator:

    m = t.matrix('FOM104D')      fetch the metadata
    m.show()                     readable summary: domain, levels, dimensions
    t.info('FOM104D')            the same metadata, as a dict
    m.where()                    the domain breadcrumb
    m.related()                  the other indicators under the same node
    m.levels                     territorial levels, e.g. ['judet', 'localitate']
    m.has_siruta                 True when localities carry a SIRUTA prefix
    m.options('Judete')          what values a dimension can take
    m.help()                     this guide, for one indicator

Lists returned by `find`, `domains` and `related` render as a table, in the
terminal and in a notebook, and carry `.recent(n)`, which orders by last update
date. `.recent(n)` fetches metadata only for the items already in that list, so
keep the list small. There is no catalogue wide recent: it would take thousands
of requests.

### Dimension roles and territorial levels

Each dimension of an indicator gets a role. Roles are derived from the `details`
block of the API response, which maps a known key to the `dimCode` of the
dimension that plays that role: `nomJud` gives `judet`, `nomLoc` gives
`localitate`, `matTime` gives `timp`, `matCaen1` and `matCaen2` give `caen`. A
dimension whose label starts with `UM:` is the unit of measure, `um`. Anything
else is `alt`.

`m.levels` lists the territorial roles present, from coarse to fine. FOM104D has
two separate territorial dimensions and so reports `['judet', 'localitate']`.

This is deliberately literal: an indicator whose `details` has `nomJud` set to 0
reports no territorial level, even when one of its dimensions mentions counties
in its label. SOM101B is such a case.

`m.options(dimension)` accepts a dimension index, a role (`timp`, `judet`,
`localitate`, and `teritoriu` for the finest territorial one present), or a
label such as `Judete`.

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
