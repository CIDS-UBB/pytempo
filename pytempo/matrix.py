"""The Matrix object: identity, metadata, and data.

The endpoint is defined by the code: everything starts from t.matrix('FOM104D').
catalog.search returns a Matrix with code, name and url; metadata is fetched on
demand.

The display types (MatrixList, TextList) live here too, so the lists returned by
search, domains and related render as a table rather than a raw dict.

A note on cost: names from the API carry embedded HTML, and levels need each
indicator's metadata. Display never fetches metadata by itself; it shows levels
only for indicators that already carry them.
"""
import html
import re
from dataclasses import dataclass, field

import pandas as pd

from . import (chunking, client, endpoints, hierarchy, incremental, manual,
               parse, selection, territory)
from .chunking import MAX_CELLS
from .models import Dimension, Node, Option

# past this many requests get() stops and sends you to download(), so nobody
# starts a download of tens of minutes in memory by accident
POLITE_REQUESTS = 50

# past this many options a dimension is worth trimming with select= before
# downloading everything it has
BIG_DIMENSION = 30

_ANCHORS = re.compile(r"<a\b[^>]*>.*?</a>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_EMPTY = re.compile(r"\(\s*\)|\[\s*\]")


def _clean(text: str) -> str:
    """Clean a name from the API so it reads well inside a breadcrumb.

    Node names carry <a href=...>text</a> anchors pointing at press releases.
    We remove the anchor together with its text, otherwise the breadcrumb turns
    into a paragraph. Empty brackets and orphan separators are cleaned up too.
    """
    if not text:
        return ""
    out = _TAGS.sub(" ", _ANCHORS.sub(" ", html.unescape(text)))
    out = _EMPTY.sub(" ", out)
    return " ".join(out.split()).strip(" ;,-")


def _role_text(dimension) -> str:
    """The role as it is shown: 'teritoriu/localitate' rather than 'teritoriu'.

    'teritoriu' covers both a county dimension and a locality one, and which is
    which is the whole question when you are looking for the fine territory.
    """
    if dimension.role == "teritoriu" and dimension.finest_level:
        return f"{dimension.role}/{dimension.finest_level}"
    return dimension.role


def _is_total(option) -> bool:
    """The aggregate option of a dimension, found by name, not by position."""
    return territory.is_total_label(option.label)


def _totals_or_all(dimension) -> list:
    """Just the total of a dimension, or everything if it carries no total."""
    totals = [o for o in dimension.options if _is_total(o)]
    return totals or list(dimension.options)


def _decision_line(m, wanted, plan, requests) -> str:
    """What was decided, in one line, before the download starts.

    The strategy shown is the one this call actually uses, not the plan's
    strategy for the whole indicator: a level filter often shrinks a by_county
    download to a single request, and saying by_county there would be a lie.
    """
    if wanted:
        level = ", ".join(wanted)
        suffix = " (the finest)" if level == plan.get("default_level") else ""
        chosen = f"level {level}{suffix}"
    else:
        chosen = "all levels" if m.levels else "no territorial filter"
    strategy = ("single" if len(requests) == 1
                else plan.get("strategy", "single"))
    count = f"{len(requests)} request" if len(requests) == 1 else \
        f"{len(requests)} requests"
    return f"{chosen}, {strategy}, {count}"


def _excluded_hint(m, wanted) -> str | None:
    """Say which levels the default left out, and how to get them back.

    Taking the finest level is usually what people want, but silently dropping
    the macroregion and region rows surprises them. Naming what was left out
    costs one line and saves a puzzled look at the row count.
    """
    if not wanted:
        return None
    left_out = [lv for lv in m.levels if lv not in wanted]
    if not left_out:
        return None
    listed = (left_out[0] if len(left_out) == 1
             else f"{', '.join(left_out[:-1])} and {left_out[-1]}")
    return f"  for every level, including {listed}, use get(level=None)"


def _too_big(cod: str, request_count: int, wanted) -> ValueError:
    """What get() says when the plan is too large to hold in memory safely.

    It used to ask at the keyboard, which reads as a hang in a notebook and
    answers itself with a no under pytest. An error that names the way out,
    for this indicator and this selection, is both honest and scriptable.
    """
    return ValueError(
        f"{cod} is large: {request_count} requests, over the "
        f"{POLITE_REQUESTS} get() holds in memory. Nothing has been "
        f"downloaded yet.\n"
        f"Do not pull this one with get(): it keeps every request in memory "
        f"until the last one, and loses all of it if a late request times "
        f"out. Use:\n"
        f"  {manual.download_line(cod, wanted)}\n"
        f"which writes each request to disk as it arrives, resumes where it "
        f"stopped, and retries on timeout. See m.how() for the whole manual.\n"
        f"Or get(confirm=False) if you really do want get().")


class TextList(list):
    """A list of strings that prints readably (breadcrumb, options)."""

    def __new__(cls, items, sep=", ", show=20):
        return super().__new__(cls, items)

    def __init__(self, items, sep=", ", show=20):
        super().__init__(items)
        self._sep = sep
        self._show = show

    def __repr__(self) -> str:
        if len(self) <= self._show:
            return self._sep.join(str(x) for x in self)
        head = self._sep.join(str(x) for x in self[:self._show])
        return f"{head}{self._sep}... ({len(self)} in total)"


class MatrixList(list):
    """The results of a search, or a list of nodes, as a table.

    It holds either Matrix or Node objects. The levels column appears only when
    EVERY element already knows its levels, from the index or from fetched
    metadata, so display never costs a request. Domains have no levels, so a
    list of domains does not get the column.
    """

    def _shows_levels(self) -> bool:
        return bool(self) and all(getattr(it, "levels_known", False)
                                  for it in self)

    def _rows(self, with_levels: bool) -> list[tuple]:
        if not with_levels:
            return [(it.code, _clean(it.name)) for it in self]
        return [(it.code, _clean(it.name), ", ".join(it.levels)) for it in self]

    def __repr__(self) -> str:
        if not self:
            return "no results"
        with_levels = self._shows_levels()
        rows = self._rows(with_levels)
        wcode = max(len(r[0]) for r in rows)
        out = []
        for row in rows:
            line = f"{row[0]:<{wcode}}  {row[1][:90]}"
            if with_levels:
                line += f"  [{row[2]}]"
            out.append(line)
        out.append(f"({len(rows)} results)")
        return "\n".join(out)

    def _repr_html_(self) -> str:
        if not self:
            return "<p>no results</p>"
        with_levels = self._shows_levels()
        header = "<th>code</th><th>name</th>" + ("<th>levels</th>" if with_levels
                                               else "")
        cells = ""
        for row in self._rows(with_levels):
            cells += (f"<tr><td><code>{html.escape(row[0])}</code></td>"
                      f"<td>{html.escape(row[1])}</td>")
            if with_levels:
                cells += f"<td>{html.escape(row[2])}</td>"
            cells += "</tr>"
        return (
            f"<table><thead><tr>{header}</tr>"
            f"</thead><tbody>{cells}</tbody></table>"
            f"<p>{len(self)} results</p>"
        )

    def recent(self, n: int = 15) -> "MatrixList":
        """The n most recently updated elements OF THIS SET.

        It fetches metadata only for the elements in the set. There is no
        catalogue wide recent: that would be thousands of calls.
        """
        loaded = [matrix(it.code) if not it.last_updated else it
                  for it in self if isinstance(it, Matrix)]
        loaded.sort(key=lambda m: _as_date(m.last_updated), reverse=True)
        return MatrixList(loaded[:n])


def _as_date(stamp: str) -> tuple:
    """'20-11-2025' becomes (2025, 11, 20), sortable. Unknown sorts last."""
    parts = (stamp or "").split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        d, m, y = parts
        return (int(y), int(m), int(d))
    return (0, 0, 0)


@dataclass
class Matrix:
    """One TEMPO indicator. After search it has code and name; the rest is
    filled in lazily."""
    code: str
    name: str = ""
    definition: str = ""
    methodology: str = ""
    observations: str = ""
    last_updated: str = ""
    periodicity: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    dimensions: list = field(default_factory=list)
    details: dict = field(default_factory=dict)
    ancestors: list = field(default_factory=list)  # [{name, code}] domain to parent
    # levels coming from the local index, when metadata has not been fetched.
    # None means unknown; an empty list means known to have none
    cached_levels: list | None = None

    @property
    def url(self) -> str:
        """The link to this indicator's metadata (GET matrix/{code})."""
        return endpoints.matrix(self.code)

    def link_ok(self) -> bool:
        """True if the indicator's link answers. Used by the link check."""
        return client.url_ok(self.url)

    @property
    def levels(self) -> list[str]:
        """The territorial levels present, from coarse to fine.

        From metadata when it has been fetched, otherwise from the index, if
        search put them there.
        """
        if self.dimensions:
            return territory.levels_present(self.dimensions, self.details)
        return list(self.cached_levels or [])

    @property
    def levels_known(self) -> bool:
        """Are the levels available without any network call?"""
        return bool(self.dimensions) or self.cached_levels is not None

    @property
    def has_siruta(self) -> bool:
        """True if locality names carry a SIRUTA prefix."""
        return bool(self.details.get("matSiruta"))

    def info(self) -> dict:
        """The full metadata, as a dictionary."""
        return {
            "code": self.code,
            "name": self.name,
            "definition": self.definition,
            "methodology": self.methodology,
            "observations": self.observations,
            "last_updated": self.last_updated,
            "periodicity": self.periodicity,
            "sources": self.sources,
            "levels": self.levels,
            "has_siruta": self.has_siruta,
            "dimensions": [
                {
                    "index": d.dim_index,
                    "code": d.dim_code,
                    "label": d.label.strip(),
                    "role": d.role,
                    "finest_level": d.finest_level,
                    "n_options": len(d.options),
                }
                for d in self.dimensions
            ],
            "territory_columns": self.territory_columns(),
        }

    @property
    def locality_dimension(self):
        """The dimension holding localities, or None when there are none.

        The way to ask, because the label is not one. FOM104D calls it
        'Localitati', POP107D calls it 'Localitati ', GOS102A calls it
        'Municipii si orase', and code that matches on the name loses the last
        one without a word: the download is correct, the columns are there
        under their own prefix, and whatever downstream was looking for
        'Localitati_siruta' quietly finds nothing.
        """
        for d in self.dimensions:
            if d.role == "teritoriu" and territory.is_locality_dimension(
                    d, self.details):
                return d
        return None

    @property
    def territory_dimension(self):
        """The finest territorial dimension, or None if there is none.

        Localities when the indicator reaches them, otherwise the first
        territorial dimension, which is the county or hierarchical one.
        """
        territorial = [d for d in self.dimensions if d.role == "teritoriu"]
        return self.locality_dimension or (territorial[0] if territorial
                                           else None)

    def territory_columns(self) -> dict:
        """The columns of the finest territory, keyed by what they hold.

        The names stay exactly as they come out of get(): the library does not
        rename anything, the dimension keeps the name INS gave it. What this
        adds is a way to find those columns without knowing that name.

            t.matrix('GOS102A').territory_columns()
            {'label': 'Municipii si orase',
             'siruta': 'Municipii si orase_siruta',
             'nivel': 'Municipii si orase_nivel',
             'tip': 'Municipii si orase_tip',
             'nume': 'Municipii si orase_nume'}

        'label' is the original column, the one carrying the INS name; the rest
        are the derived ones, and only those this dimension's options justify
        appear. An indicator with no territorial dimension gives an empty dict.
        """
        self._ensure_meta()
        dimension = self.territory_dimension
        if dimension is None:
            return {}
        column = dimension.label.strip()
        columns = {"label": column}
        for key in territory.derived_keys(dimension):
            columns[key] = f"{column}_{key}"
        return columns

    def _ensure_meta(self) -> "Matrix":
        """Fetch metadata if it is not already there (search returns only
        code and name)."""
        if not self.dimensions and not self.ancestors:
            fresh = matrix(self.code)
            for f in fresh.__dataclass_fields__:
                setattr(self, f, getattr(fresh, f))
        return self

    def _breadcrumb(self) -> TextList:
        """Just the path through domains, from the top domain to the indicator."""
        self._ensure_meta()
        names = [_clean(a.get("name", "")) for a in self.ancestors]
        return TextList([n for n in names if n], sep=" > ", show=10)

    def what(self) -> None:
        """The essence of the indicator, in a few lines. describe() is the
        full record."""
        self._ensure_meta()
        print(f"{self.code}  {_clean(self.name)}")
        definition = (self.definition or "").strip()
        if definition:
            first_sentence = re.split(r"\.\s", definition, maxsplit=1)[0].strip()
            print(f"  {first_sentence}.")
        units = [_clean(d.label).split(":", 1)[-1].strip()
              for d in self.dimensions if d.role == "um"]
        if units:
            print(f"  unit        : {', '.join(units)}")
        if self.periodicity:
            print(f"  periodicity : {', '.join(self.periodicity)}")
        if self.last_updated:
            print(f"  updated     : {self.last_updated}")
        years = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b",
                                    self.observations or "")))
        if years:
            print(f"  warning     : the observations mention the years "
                  f"{', '.join(years)}, so there may be series breaks")
            print("                read them with .describe()")

    def where(self) -> None:
        """Where the indicator sits and what it covers: domain, territory,
        years."""
        self._ensure_meta()
        crumbs = self._breadcrumb()
        if crumbs:
            print(f"domain   : {crumbs!r}")

        for d in self.dimensions:
            if d.role != "teritoriu":
                continue
            print(f"territory: {_clean(d.label)} ({len(d.options)} options)")
            per_level = manual.dimension_units(d, self.details)
            for level_name in territory._LEVEL_ORDER:
                if level_name in per_level:
                    print(f"    {level_name:15} {per_level[level_name]}")
        if not self.levels:
            print("territory: none, this indicator is not territorial")
        else:
            print(f"SIRUTA   : {'yes' if self.has_siruta else 'no'}")

        for d in self.dimensions:
            if d.role != "timp":
                continue
            years = [parse._year_of(o.label) for o in d.options]
            years = [a for a in years if a]
            span = f"{min(years)} to {max(years)}" if years else "unknown"
            print(f"time     : {_clean(d.label)}, {len(d.options)} periods, "
                  f"{span}")

    def _how_large(self, request_count: int, default_level) -> None:
        """The first thing to say about a large indicator: do not use get().

        At the bottom of the printout this was a footnote to be scrolled to,
        after a list of get() calls that will not run. It belongs first.
        """
        wanted = [default_level] if default_level else []
        print()
        print(f"  THIS ONE IS LARGE: {request_count} requests. get() stops "
              f"and sends you here.")
        print("  Download it safely, with a checkpoint and a resume:")
        print(f"    {manual.download_line(self.code, wanted)}")
        print("  download() writes each slice to disk as it arrives, picks up "
              "where it")
        print("  stopped if it breaks, and retries when INS times out.")
        print()
        print("  the selection arguments below work on either one: get() for "
              "a small")
        print("  slice of it, download() for the whole thing.")

    def _requests_for(self, wanted, select: dict | None = None) -> int:
        """How many requests one selection would take. Zero if it cannot plan.

        The whole manual is built on this: what a level costs, what a filter
        saves, and which of get() and download() to print for each. Planning is
        arithmetic on lists, so asking it once per level costs milliseconds.
        """
        try:
            target = selection.restrict(self, select) if select else self
            return len(chunking.plan_requests(
                target, target._build_selection(wanted)))
        except ValueError:
            # a filter that matches nothing, or a level this indicator does
            # not have: say nothing rather than fail inside a help method
            return 0

    def _request_count(self, plan) -> int:
        """How many requests get() would really send, on its default call.

        Not the registry's estimate, which counts one request per county for a
        by_county matrix: right about the strategy, wrong about the number.
        POP107D splits every county again on its 104 ages, so its 43 counties
        are 380 requests. A manual that promises 43 and a get() that refuses
        380 cannot both be right, and the one that has to be right is the
        manual.
        """
        wanted = self._wanted_levels("finest", None, plan)
        return self._requests_for(wanted) or plan.get("est_requests", 1)

    def how(self) -> None:
        """This indicator's own download manual, ready to copy."""
        self._ensure_meta()
        plan = self.fetch_plan()
        strategy = plan.get("strategy", "single")
        request_count = self._request_count(plan)
        default_level = plan.get("default_level")
        large = request_count > POLITE_REQUESTS

        print(f"How to download {self.code}:")
        print(f"  m = t.matrix({self.code!r})")
        if large:
            self._how_large(request_count, default_level)
        print(f"  df = m.get()          "
              f"{'level ' + default_level if default_level else 'no territorial filter'}"
              f", tidied")
        print("  m.get(raw=True)       exactly what INS returns, no extras")
        if not large:
            print(f"  {manual.download_line(self.code, [])}")
            print("                        the same data, written straight to "
                  "a CSV on disk")

        territorial = [d for d in self.dimensions if d.role == "teritoriu"]
        if default_level:
            manual.print_levels(self, default_level, POLITE_REQUESTS)
            if len(territorial) > 1:
                print()
                print("  county and locality are separate dimensions here, so "
                      "a level picks")
                print("  which one is active and puts the other on TOTAL: "
                      "level='judet' gives")
                print("  one row per county in a single request, level="
                      "'localitate' gives the")
                print("  localities, county by county.")
        else:
            reason = ("this indicator is not territorial" if not territorial
                     else "its territorial names are not administrative units")
            print(f"  (the level filter does not apply here: {reason},")
            print("   so get() takes everything)")

        manual.print_filters(self, BIG_DIMENSION)
        manual.print_example(self, default_level, POLITE_REQUESTS)

        print()
        print(f"  strategy: {strategy}, {request_count} "
              f"{'request' if request_count == 1 else 'requests'}")
        if large:
            print(f"  over {POLITE_REQUESTS} requests, so download() rather "
                  f"than get(), as above")
        elif request_count > 1:
            print("  downloaded in several requests and concatenated")

    def schema(self, schema: str = "tempo", include_comments: bool = True) -> str:
        """PostgreSQL DDL for this indicator, as text. Nothing is executed."""
        from . import schema as schema_mod  # local: keeps the import graph flat

        return schema_mod.table_ddl(self, schema=schema,
                                    include_comments=include_comments)

    def related(self, limit: int = 25) -> MatrixList:
        """The other indicators under the same parent node."""
        self._ensure_meta()
        if not self.ancestors:
            return MatrixList([])
        parent = self.ancestors[-1].get("code", "")
        node = client.get_json(endpoints.context(parent)) or {}
        out = []
        for child in node.get("children") or []:
            if child.get("url") != "matrix" or child.get("code") == self.code:
                continue
            out.append(Matrix(code=child["code"], name=_clean(child.get("name", ""))))
            if len(out) >= limit:
                break
        return MatrixList(out)

    def _find_dimension(self, dimension):
        """Resolve a dimension by index, role or label."""
        if isinstance(dimension, int):
            return self.dimensions[dimension]

        want = _clean(str(dimension)).lower()
        terr = [d for d in self.dimensions if d.role == "teritoriu"]
        # 'teritoriu' gives the finest territorial dimension present, the same
        # one territory_columns() names
        if want == "teritoriu" and terr:
            return self.territory_dimension
        # a level ('judet', 'localitate', ...) gives the dimension covering it
        if want in territory._LEVEL_ORDER:
            hit = [d for d in terr
                   if want in territory.dimension_levels(d, self.details)]
            if hit:
                return hit[0]
        hit = [d for d in self.dimensions if d.role == want]
        if hit:
            return hit[0]
        hit = [d for d in self.dimensions if _clean(d.label).lower() == want]
        if hit:
            return hit[0]
        hit = [d for d in self.dimensions if want in _clean(d.label).lower()]
        if hit:
            return hit[0]

        available = ", ".join(f"{d.label.strip()} ({_role_text(d)})"
                            for d in self.dimensions)
        raise ValueError(
            f"unknown dimension: {dimension!r}. Available: {available}")

    def options(self, dimension=None, limit: int | None = None,
                kind: str | None = None) -> TextList:
        """The option names of a dimension, so you know what you can filter on.

        With no argument it lists the indicator's dimensions, with their role
        and how many options each has, so you can see what to ask for.

        dimension accepts an index, a role ('timp', 'judet', 'teritoriu') or a
        label ('Judete'). limit truncates the returned list.

        kind narrows a hierarchical dimension to one level, with the same words
        select= takes: 'groups' or 'parents' for the aggregates, 'leaves' for
        the finest level, 'total' for the total alone. It is there so you can
        see what a select= would keep before downloading anything:

            m.options('varsta', kind='groups')   the 19 age groups
            m.get(select={'varsta': 'groups'})   the same 19, downloaded

        Without kind, every option, exactly as before.
        """
        self._ensure_meta()
        if dimension is None:
            return TextList(
                [f"[{d.dim_index}] {_clean(d.label)} ({_role_text(d)}, "
                 f"{len(d.options)} options)" for d in self.dimensions],
                sep="\n", show=50)

        dim = self._find_dimension(dimension)
        chosen = hierarchy.pick(dim, kind) if kind else dim.options
        labels = [o.label for o in chosen]
        if limit is not None:
            labels = labels[:limit]
        return TextList(labels)

    def show(self) -> None:
        """A readable summary: where it sits, its levels, its dimensions."""
        self._ensure_meta()
        print(f"{self.code}  {_clean(self.name)}")
        crumbs = self._breadcrumb()
        if crumbs:
            print(f"  domain    : {crumbs!r}")
        if self.levels:
            print(f"  levels    : {', '.join(self.levels)}")
        if self.last_updated:
            print(f"  updated   : {self.last_updated}")
        if self.periodicity:
            print(f"  periodic  : {', '.join(self.periodicity)}")
        print("  dimensions:")
        for d in self.dimensions:
            print(f"    [{d.dim_index}] {_clean(d.label)} ({_role_text(d)}, "
                  f"{len(d.options)} options)")

    def describe(self) -> None:
        """The full record, with every word INS wrote, untruncated.

        show() is the short summary and does not touch the texts. Here you
        read all of it: the definition, the methodology, the sources and the
        observations, which is where series breaks and warnings about
        incomplete years live.
        """
        self._ensure_meta()
        print(f"{self.code}  {_clean(self.name)}")
        crumbs = self._breadcrumb()
        if crumbs:
            print(f"domain      : {crumbs!r}")
        if self.levels:
            print(f"levels      : {', '.join(self.levels)}")
        if self.periodicity:
            print(f"periodicity : {', '.join(self.periodicity)}")
        if self.last_updated:
            print(f"updated     : {self.last_updated}")

        for heading, text in (("DEFINITION", self.definition),
                            ("METHODOLOGY", self.methodology)):
            if text and text.strip():
                print(f"\n{heading}\n{text.strip()}")

        if self.sources:
            print("\nSOURCES")
            for s in self.sources:
                name = s.get("nume") if isinstance(s, dict) else str(s)
                # no _clean here: a source name carries the INS marker
                # <<6263>>, which HTML cleaning would eat
                if name and name.strip():
                    print(f"  {name.strip()}")

        if self.observations and self.observations.strip():
            print(f"\nOBSERVATIONS\n{self.observations.strip()}")

    def help(self) -> None:
        """What you can do with one indicator."""
        print(f"""Indicator {self.code}. What you can do with it:

  .what()              what it measures: definition, unit, how often
  .where()             where it sits and what it covers
  .how()               its own menu: every level, every filter, with the
                       calls to copy and what each of them costs
  .show()              short summary: domain, levels, dimensions
  .describe()          the full record: definition, methodology, sources
  .info()              the same metadata, as a dictionary
  .related()           the other indicators under the same node
  .levels              levels, e.g. ['national', 'judet', 'localitate']
  .has_siruta          True if localities carry a SIRUTA prefix
  .locality_dimension  the dimension holding localities, or None
  .territory_columns() the columns of the fine territory, by what they hold
  .options()           which dimensions it has, with role and size
  .options('teritoriu') what values one dimension takes
  .options('varsta', kind='groups')   just the aggregates of a hierarchy
  .get()               the data, as a long format DataFrame
  .get(level='judet')  one territorial level only
  .get(select={{'Sexe': ['Masculin']}})  keep only some options of a dimension
  .get(select={{'varsta': 'groups'}})  or a kind: groups, leaves, total
  .get(raw=True)       exactly what INS returns, no derived columns
  .get(progress=True)  report progress on large indicators
  .download(folder='data/x')   for large ones: to disk, checkpointed,
                       resumable, and it retries when INS times out
  .download(folder=..., return_df=False)   returns the CSV path, not the frame
  .how()               says which of the two this indicator needs
  df.tempo.spot_check(2)       on the result: two random units to check by hand

get() holds everything in memory and is right below 50 requests. Above that it
stops and points here: download() writes every request to disk as it arrives,
so an interrupted run keeps what it had and rerunning asks only for the rest.

Every download ends with a check on the joining: slices that never arrived,
rows lost or doubled, a combination of dimensions that repeats, a select that
came back the wrong size. Anything odd is printed, and the frame carries the
same verdict in df.attrs['complete'] and df.attrs['aggregation_warnings'].

The columns keep the names INS gave. To find the fine territory without
knowing that name, ask: .locality_dimension is the dimension holding
localities, called 'Localitati' in one indicator and 'Municipii si orase' in
the next, and .territory_columns() gives its column names keyed by what they
hold, ready for a rename downstream.

Missing is not zero: INS writes ':' for a figure it does not have and '0' for a
measured zero. A ':' comes back as no row at all, a '0' as a row with 0.0. The
result is not a complete grid, so an absent year is unknown until you decide
otherwise.""")

    def _territorial_options(self, d, wanted: list[str], locality_active: bool):
        """Which options of one territorial dimension to send.

        A locality dimension stands for exactly one level, so it is either all
        of its localities or just its total. A hierarchical dimension is cut by
        the level of each option name.
        """
        if territory.is_locality_dimension(d, self.details):
            if "localitate" in wanted:
                return [o for o in d.options if not _is_total(o)]
            return _totals_or_all(d)

        if locality_active:
            # the data is keyed by the real county and locality pair, so
            # pinning the county to its total returns nothing at all. Verified
            # against INS: county TOTAL crossed with real localities gives zero
            # rows. When localities are the active dimension the county one
            # stays whole and the county by county split pairs them up.
            return list(d.options)

        matching = [o for o in d.options
                     if territory.option_level(o.label) in wanted]
        return matching or _totals_or_all(d)

    def _build_selection(self, wanted: list[str]) -> list[list[int]]:
        """The nomItemIds to send, per dimension, in dimensionsMap order.

        With no levels requested it takes everything. With levels requested it
        trims only the territorial dimensions; the rest stay complete.

        When county and locality are two separate dimensions, the level picks
        which one is active and puts the other on its total:
        level='judet' gives one row per county, with localities on TOTAL, in a
        single request; level='localitate' gives the localities, keeping the
        county dimension whole so the county by county split can pair them.
        """
        if not wanted:
            return [[o.nom_item_id for o in d.options] for d in self.dimensions]

        for lv in wanted:
            if lv not in self.levels:
                raise territory.level_error(lv, self.levels, cod=self.code)

        locality_active = "localitate" in wanted and any(
            territory.is_locality_dimension(d, self.details)
            for d in self.dimensions if d.role == "teritoriu")

        per_dimension = []
        for d in self.dimensions:
            if d.role != "teritoriu":
                per_dimension.append([o.nom_item_id for o in d.options])
            else:
                per_dimension.append([o.nom_item_id for o in
                                      self._territorial_options(d, wanted,
                                                                locality_active)])
        return per_dimension

    def fetch_plan(self) -> dict:
        """The fetch plan: from the registry if it is there, else computed.

        The registry ships with the package, so normally the plan is already
        written. The fallback keeps the library working without a registry.
        """
        from . import schemas  # local import: schemas imports matrix, else a cycle

        try:
            registry = schemas.load_registry()
        except ValueError:
            registry = None
        record = (registry or {}).get("entries", {}).get(self.code, {})
        plan = record.get("fetch_plan")
        if plan:
            return plan

        self._ensure_meta()
        return schemas.plan_for({
            "dims": [{"label": d.label.strip(), "role": d.role,
                      "n_options": len(d.options), "dim_code": d.dim_code}
                     for d in self.dimensions],
            "levels": self.levels,
            "total_cells": chunking.cells(
                [[o.nom_item_id for o in d.options] for d in self.dimensions]),
            "family": ("judet_localitate"
                       if any(territory.is_locality_dimension(d, self.details)
                              for d in self.dimensions) else "alt"),
        })

    def _wanted_levels(self, level, levels, plan) -> list[str]:
        """The levels actually requested, after resolving 'finest'.

        An explicit list in levels beats the default: someone who writes
        levels=['judet', 'regiune'] has already said what they want.
        """
        explicit_levels = list(levels or [])
        if isinstance(level, str) and level != "finest":
            explicit_levels = [level] + explicit_levels
        if explicit_levels:
            return explicit_levels
        if level != "finest":
            return []               # level=None asks for everything

        default_level = plan.get("default_level")
        territorial = [d for d in self.dimensions if d.role == "teritoriu"]
        # with county plus locality, the finest level means the whole
        # download: by_county already delivers the localities
        if not default_level or len(territorial) > 1:
            return []
        return [default_level]

    def _plan_requests(self, level, levels, select):
        """The payloads to send, and the matrix they were built from.

        get() and download() differ in what they do with the answers, not in
        what they ask for, so the whole decision, select, level, selection and
        chunking, is taken here, once.
        """
        self._ensure_meta()
        plan = self.fetch_plan()
        target = selection.restrict(self, select) if select else self
        wanted = target._wanted_levels(level, levels, plan)
        chosen = target._build_selection(wanted)
        return target, wanted, plan, chunking.plan_requests(target, chosen)

    def _announce(self, target, wanted, plan, requests) -> None:
        """The decision, in the shape both get() and download() print it."""
        print(f"{self.code}: {_decision_line(target, wanted, plan, requests)}")
        for line in selection.summary(self, target):
            print(line)
        hint = _excluded_hint(target, wanted)
        if hint:
            print(hint)

    def download(self, level: territory.Level | str | None = "finest",
                 levels: list[territory.Level] | None = None,
                 select: dict | None = None,
                 folder=None, out=None, return_df: bool = True,
                 resume: bool = True, tidy: bool = True, raw: bool = False,
                 progress: bool = True):
        """The data, fetched through disk, for indicators too large for get().

        Same selection as get(): level, levels and select mean exactly what they
        mean there, and the plan is built by the same code. What changes is
        where the answers go. Each request is written to its own slice file the
        moment it arrives, so memory stays at one request and an interrupted
        download keeps what it had. At the end the slices are read back,
        concatenated, tidied, written as one CSV, and removed.

        folder is where the slices and the CSV go. With no folder it works in a
        temporary directory and cleans it up, which is fine when you want the
        frame and nothing else.

        out is the path of the final CSV; by default it is <code>.csv inside
        folder. return_df=False returns that path instead of the frame and
        never holds the whole thing in memory, which is the point for the
        largest indicators.

        resume=True, the default, skips the requests whose slice is already on
        disk, so rerunning after a failure asks only for what is missing. A
        request that keeps failing is reported at the end rather than sinking
        the rest of the download.

        Whatever it returns, the joining is checked and anything odd is said
        out loud: slices that never arrived, rows lost or doubled, a repeated
        combination of dimensions, a select that did not come back the size it
        was asked for. The frame carries the same verdict in df.attrs, under
        complete, missing_requests and aggregation_warnings.

        Missing is not zero here either: a ':' from INS is an absent row and a
        '0' is a row with 0.0, exactly as in get(). A CSV of a large indicator
        is therefore sparse by nature, and a row that is not in it is a figure
        INS does not have, not a zero.
        """
        target, wanted, plan, requests = self._plan_requests(level, levels,
                                                             select)
        if progress:
            self._announce(target, wanted, plan, requests)
        return incremental.run(target, requests, folder=folder, out=out,
                               return_df=return_df, resume=resume, tidy=tidy,
                               raw=raw, progress=progress, select=select)

    def get(self, level: territory.Level | str | None = "finest",
            levels: list[territory.Level] | None = None,
            select: dict | None = None,
            tidy: bool = True, progress="auto", raw: bool = False,
            confirm: bool = True):
        """The indicator's data, as a long format DataFrame.

        It executes the plan from the registry: read the strategy, run it,
        apply tidy.

        level='finest' (the default) takes the finest level the indicator
        actually reaches; for non territorial matrices it filters nothing.
        level=None asks for everything. A specific level is named as such,
        for example level='judet'.

        select={'Grupe de varsta': ['25-34 ani']} keeps only some options of a
        dimension, so you do not have to download every option of every one.
        The key is a dimension label, matched exactly or as a unique substring;
        the value is a list of nomItemIds, a list of option labels, or a
        predicate on the option. Dimensions select does not name stay whole.
        It applies before the query is built, so the cell count and the
        chunking work on the smaller set.

        select and level are independent and compose in that order: select
        narrows the options of the dimension it names, then the level logic
        runs on what is left. Selecting a few counties and asking for
        level='judet' gives those counties, not all of them.

        tidy=True adds the derived columns; raw=True returns exactly what INS
        returned. progress='auto' only speaks when the plan has more than one
        request.

        Over POLITE_REQUESTS requests it stops and points at download(), which
        checkpoints on disk and can resume. confirm=False goes ahead anyway,
        everything in memory, for anyone who knows what they are doing.

        Missing is not zero. INS writes ':' for a figure it does not have and
        '0' for a measured zero, and those are different statements. The
        distinction survives: a ':' arrives as no row at all, so the
        combination is simply absent from the result, and a '0' arrives as a
        row whose Valoare is 0.0. The frame is therefore not a complete grid,
        and joining or averaging over it is a decision: an absent year is
        unknown, not zero, unless you decide otherwise.
        """
        target, wanted, plan, requests = self._plan_requests(level, levels,
                                                             select)

        speaks = (len(requests) > 1) if progress == "auto" else bool(progress)
        if progress is not False:
            self._announce(target, wanted, plan, requests)
        if confirm and len(requests) > POLITE_REQUESTS:
            raise _too_big(self.code, len(requests), wanted)

        frames = []
        for i, payload in enumerate(requests, 1):
            frames.append(parse.pivot_csv_to_dataframe(
                client.post_pivot(payload), target))
            if speaks:
                total = sum(len(c) for c in frames)
                print(f"  {i}/{len(requests)}: +{len(frames[-1])} rows "
                      f"(total {total})")

        df = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
        return df if raw or not tidy else parse.standardize(df, target)

    def _repr_html_(self) -> str:
        """The card of a single indicator. Here the levels really are known.

        It does not fetch metadata by itself: a Matrix coming from search is
        shown with what it has, so displaying it in a notebook never triggers
        a GET.
        """
        rows = []
        if self.levels:
            rows.append(("levels", ", ".join(self.levels)))
        if self.last_updated:
            rows.append(("updated", self.last_updated))
        if self.periodicity:
            rows.append(("periodicity", ", ".join(self.periodicity)))
        if self.ancestors:
            rows.append(("where", repr(self._breadcrumb())))
        meta = "".join(
            f"<tr><th align='left'>{html.escape(k)}</th>"
            f"<td>{html.escape(v)}</td></tr>" for k, v in rows
        )
        dims = "".join(
            f"<tr><td>{d.dim_index}</td><td>{html.escape(_clean(d.label))}</td>"
            f"<td>{html.escape(_role_text(d))}</td><td>{len(d.options)}</td></tr>"
            for d in self.dimensions
        )
        out = [f"<p><code>{html.escape(self.code)}</code> "
               f"<b>{html.escape(_clean(self.name))}</b></p>"]
        if meta:
            out.append(f"<table><tbody>{meta}</tbody></table>")
        if dims:
            out.append(
                "<table><thead><tr><th>#</th><th>dimension</th><th>role</th>"
                f"<th>options</th></tr></thead><tbody>{dims}</tbody></table>")
        return "".join(out)

    def __repr__(self) -> str:
        return f"Matrix({self.code!r}, {self.name!r})"


def _build(cod: str, data: dict) -> Matrix:
    """Build a Matrix from the raw JSON of the matrix/{code} endpoint.

    The dimension order from dimensionsMap is kept in dim_index: it drives the
    order inside encQuery.
    """
    details = data.get("details") or {}
    dims = []
    for i, raw in enumerate(data.get("dimensionsMap") or []):
        options = [
            Option(
                label=opt.get("label", ""),
                nom_item_id=opt.get("nomItemId"),
                offset=opt.get("offset"),
                parent_id=opt.get("parentId"),
            )
            for opt in (raw.get("options") or [])
        ]
        dims.append(Dimension(
            label=raw.get("label", ""),
            dim_code=raw.get("dimCode"),
            dim_index=i,
            options=options,
        ))
    territory.assign_roles(dims, details)

    return Matrix(
        code=cod,
        name=data.get("matrixName", ""),
        definition=data.get("definitie", "") or "",
        methodology=data.get("metodologie", "") or "",
        observations=data.get("observatii", "") or "",
        last_updated=data.get("ultimaActualizare", "") or "",
        periodicity=data.get("periodicitati") or [],
        sources=data.get("surseDeDate") or [],
        dimensions=dims,
        details=details,
        ancestors=[a for a in (data.get("ancestors") or []) if a.get("code")],
    )


def matrix(cod: str, refresh: bool = False) -> Matrix:
    """Build a Matrix by fetching its metadata (GET matrix/{code}).

    It checks the code against the cached catalogue first: for a code that
    does not exist INS returns non JSON, and the raw error helps nobody.
    refresh=True bypasses the metadata cache.
    """
    from . import catalog  # local import: catalog imports matrix, else a cycle

    cod = (cod or "").strip().upper()
    if cod not in catalog.name_dict():
        raise ValueError(
            f"Code '{cod}' does not exist in TEMPO. Search with t.find(...).")
    data = client.get_json(endpoints.matrix(cod), use_cache=not refresh)
    return _build(cod, data)


def info(cod: str) -> dict:
    """Shortcut: one indicator's metadata."""
    return matrix(cod).info()


def get(cod: str, level: territory.Level | str | None = "finest",
        levels: list[territory.Level] | None = None,
        select: dict | None = None,
        tidy: bool = True, progress="auto", raw: bool = False,
        confirm: bool = True):
    """Shortcut: one indicator's data, as a DataFrame.

    Exactly Matrix.get, starting from a code, defaults included.
    """
    return matrix(cod).get(level=level, levels=levels, select=select, tidy=tidy,
                           progress=progress, raw=raw, confirm=confirm)


def download(cod: str, level: territory.Level | str | None = "finest",
             levels: list[territory.Level] | None = None,
             select: dict | None = None,
             folder=None, out=None, return_df: bool = True,
             resume: bool = True, tidy: bool = True, raw: bool = False,
             progress: bool = True):
    """Shortcut: one indicator's data, fetched through disk, with a checkpoint.

    Exactly Matrix.download, starting from a code, defaults included.
    """
    return matrix(cod).download(level=level, levels=levels, select=select,
                                folder=folder, out=out, return_df=return_df,
                                resume=resume, tidy=tidy, raw=raw,
                                progress=progress)
