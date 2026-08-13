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

from . import chunking, client, endpoints, parse, territory
from .chunking import MAX_CELLS
from .models import Dimension, Node, Option

# past this many requests we ask first, so nobody starts a download of tens
# of minutes by accident
POLITE_REQUESTS = 50

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


def _decision_line(m, wanted, plan, planuri) -> str:
    """What was decided, in one line, before the download starts."""
    if wanted:
        nivel = ", ".join(wanted)
        coada = " (finest)" if nivel == plan.get("default_level") else ""
        bucata = f"level {nivel}{coada}"
    else:
        bucata = "all levels" if m.levels else "no territorial filter"
    strategie = plan.get("strategy", "single")
    cereri = f"{len(planuri)} request" if len(planuri) == 1 else \
        f"{len(planuri)} requests"
    return f"{bucata}, {strategie}, {cereri}"


def _ask_big(cod: str, cereri: int) -> bool:
    print(f"{cod}: {cereri} requests, several minutes of work.")
    try:
        return input("Continue? [y/N] ").strip().lower() in ("y", "yes", "d",
                                                            "da")
    except (EOFError, OSError):
        return False


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

    def _rows(self, cu_nivele: bool) -> list[tuple]:
        if not cu_nivele:
            return [(it.code, _clean(it.name)) for it in self]
        return [(it.code, _clean(it.name), ", ".join(it.levels)) for it in self]

    def __repr__(self) -> str:
        if not self:
            return "no results"
        cu_nivele = self._shows_levels()
        rows = self._rows(cu_nivele)
        wcode = max(len(r[0]) for r in rows)
        out = []
        for row in rows:
            linie = f"{row[0]:<{wcode}}  {row[1][:90]}"
            if cu_nivele:
                linie += f"  [{row[2]}]"
            out.append(linie)
        out.append(f"({len(rows)} results)")
        return "\n".join(out)

    def _repr_html_(self) -> str:
        if not self:
            return "<p>no results</p>"
        cu_nivele = self._shows_levels()
        antet = "<th>code</th><th>name</th>" + ("<th>levels</th>" if cu_nivele
                                               else "")
        cells = ""
        for row in self._rows(cu_nivele):
            cells += (f"<tr><td><code>{html.escape(row[0])}</code></td>"
                      f"<td>{html.escape(row[1])}</td>")
            if cu_nivele:
                cells += f"<td>{html.escape(row[2])}</td>"
            cells += "</tr>"
        return (
            f"<table><thead><tr>{antet}</tr>"
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
                    "n_options": len(d.options),
                }
                for d in self.dimensions
            ],
        }

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
        definitie = (self.definition or "").strip()
        if definitie:
            prima = re.split(r"\.\s", definitie, maxsplit=1)[0].strip()
            print(f"  {prima}.")
        um = [_clean(d.label).split(":", 1)[-1].strip()
              for d in self.dimensions if d.role == "um"]
        if um:
            print(f"  unit        : {', '.join(um)}")
        if self.periodicity:
            print(f"  periodicity : {', '.join(self.periodicity)}")
        if self.last_updated:
            print(f"  updated     : {self.last_updated}")
        ani = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b",
                                    self.observations or "")))
        if ani:
            print(f"  warning     : the observations mention the years "
                  f"{', '.join(ani)}, so there may be series breaks")
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
            if territory.is_locality_dimension(d, self.details):
                print(f"    localitate      {len(d.options)}")
            else:
                pe_nivel = {}
                for o in d.options:
                    nivel = territory.option_level(o.label)
                    pe_nivel[nivel] = pe_nivel.get(nivel, 0) + 1
                for nivel in territory._LEVEL_ORDER:
                    if nivel in pe_nivel:
                        print(f"    {nivel:15} {pe_nivel[nivel]}")
        if not self.levels:
            print("territory: none, this indicator is not territorial")
        else:
            print(f"SIRUTA   : {'yes' if self.has_siruta else 'no'}")

        for d in self.dimensions:
            if d.role != "timp":
                continue
            ani = [parse._year_of(o.label) for o in d.options]
            ani = [a for a in ani if a]
            interval = f"{min(ani)} to {max(ani)}" if ani else "unknown"
            print(f"time     : {_clean(d.label)}, {len(d.options)} periods, "
                  f"{interval}")

    def how(self) -> None:
        """This indicator's own download manual, ready to copy."""
        self._ensure_meta()
        plan = self.fetch_plan()
        strategie = plan.get("strategy", "single")
        cereri = plan.get("est_requests", 1)
        implicit = plan.get("default_level")

        print(f"How to download {self.code}:")
        print(f"  m = t.matrix({self.code!r})")
        print(f"  df = m.get()          "
              f"{'level ' + implicit if implicit else 'no territorial filter'}"
              f", tidied")
        teritoriale = [d for d in self.dimensions if d.role == "teritoriu"]
        if len(teritoriale) > 1:
            # the level filter does not work when county and locality are
            # separate dimensions; do not suggest what would raise
            print("  (the level filter does not apply here: county and "
                  "locality are")
            print("   separate dimensions, and get() brings both anyway)")
        elif not implicit:
            motiv = ("this indicator is not territorial" if not teritoriale
                     else "its territorial names are not administrative units")
            print(f"  (the level filter does not apply here: {motiv},")
            print("   so get() takes everything)")
        else:
            for nivel in self.levels:
                if nivel != implicit:
                    print(f"  m.get(level={nivel!r})")
            if self.levels:
                print("  m.get(level=None)     every level at once")
        print("  m.get(raw=True)       exactly what INS returns, no extras")
        print()
        print(f"  strategy: {strategie}, roughly {cereri} "
              f"{'request' if cereri == 1 else 'requests'}")
        if cereri > POLITE_REQUESTS:
            print(f"  WARNING: over {POLITE_REQUESTS} requests, this takes a "
                  f"while. get() asks first;")
            print("  pass confirm=False when running from a script.")
        elif cereri > 1:
            print("  downloaded in several requests and concatenated")

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
        # 'teritoriu' gives the finest territorial dimension present
        if want == "teritoriu" and terr:
            fine = [d for d in terr
                    if "localitate" in territory.dimension_levels(d, self.details)]
            return (fine or terr)[0]
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

        avem = ", ".join(f"{d.label.strip()} ({d.role})" for d in self.dimensions)
        raise ValueError(
            f"unknown dimension: {dimension!r}. Available: {avem}")

    def options(self, dimension=None, limit: int | None = None) -> TextList:
        """The option names of a dimension, so you know what you can filter on.

        With no argument it lists the indicator's dimensions, with their role
        and how many options each has, so you can see what to ask for.

        dimension accepts an index, a role ('timp', 'judet', 'teritoriu') or a
        label ('Judete'). limit truncates the returned list.
        """
        self._ensure_meta()
        if dimension is None:
            return TextList(
                [f"[{d.dim_index}] {_clean(d.label)} ({d.role}, "
                 f"{len(d.options)} options)" for d in self.dimensions],
                sep="\n", show=50)

        dim = self._find_dimension(dimension)
        labels = [o.label for o in dim.options]
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
            print(f"    [{d.dim_index}] {_clean(d.label)} ({d.role}, "
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

        for titlu, text in (("DEFINITION", self.definition),
                            ("METHODOLOGY", self.methodology)):
            if text and text.strip():
                print(f"\n{titlu}\n{text.strip()}")

        if self.sources:
            print("\nSOURCES")
            for s in self.sources:
                nume = s.get("nume") if isinstance(s, dict) else str(s)
                # no _clean here: a source name carries the INS marker
                # <<6263>>, which HTML cleaning would eat
                if nume and nume.strip():
                    print(f"  {nume.strip()}")

        if self.observations and self.observations.strip():
            print(f"\nOBSERVATIONS\n{self.observations.strip()}")

    def help(self) -> None:
        """What you can do with one indicator."""
        print(f"""Indicator {self.code}. What you can do with it:

  .what()              what it measures: definition, unit, how often
  .where()             where it sits and what it covers
  .how()               its own download manual, ready to copy
  .show()              short summary: domain, levels, dimensions
  .describe()          the full record: definition, methodology, sources
  .info()              the same metadata, as a dictionary
  .related()           the other indicators under the same node
  .levels              levels, e.g. ['national', 'judet', 'localitate']
  .has_siruta          True if localities carry a SIRUTA prefix
  .options()           which dimensions it has, with role and size
  .options('teritoriu') what values one dimension takes
  .get()               the data, as a long format DataFrame
  .get(level='judet')  one territorial level only
  .get(raw=True)       exactly what INS returns, no derived columns
  .get(progress=True)  report progress on large indicators""")

    def _build_selection(self, wanted: list[str]) -> list[list[int]]:
        """The nomItemIds to send, per dimension, in dimensionsMap order.

        With no levels requested it takes everything. With levels requested it
        trims only the territorial dimension; the rest stay complete.
        """
        if not wanted:
            return [[o.nom_item_id for o in d.options] for d in self.dimensions]

        for lv in wanted:
            if lv not in self.levels:
                raise territory.level_error(lv, self.levels, cod=self.code)

        terr = [d for d in self.dimensions if d.role == "teritoriu"]
        if len(terr) > 1:
            raise NotImplementedError(
                "filtru pe nivel pentru matrice cu judet plus localitate "
                "separate: iteratia 3c")

        selection = []
        for d in self.dimensions:
            if d.role != "teritoriu":
                selection.append([o.nom_item_id for o in d.options])
            elif (territory.is_locality_dimension(d, self.details)
                  and "localitate" in wanted):
                selection.append([o.nom_item_id for o in d.options])
            else:
                selection.append([o.nom_item_id for o in d.options
                                  if territory.option_level(o.label) in wanted])
        return selection

    def fetch_plan(self) -> dict:
        """The fetch plan: from the registry if it is there, else computed.

        The registry ships with the package, so normally the plan is already
        written. The fallback keeps the library working without a registry.
        """
        from . import schemas  # local import: schemas imports matrix, else a cycle

        try:
            registru = schemas.load_registry()
        except ValueError:
            registru = None
        fisa = (registru or {}).get("entries", {}).get(self.code, {})
        plan = fisa.get("fetch_plan")
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
        explicite = list(levels or [])
        if isinstance(level, str) and level != "finest":
            explicite = [level] + explicite
        if explicite:
            return explicite
        if level != "finest":
            return []               # level=None asks for everything

        implicit = plan.get("default_level")
        teritoriale = [d for d in self.dimensions if d.role == "teritoriu"]
        # with county plus locality, the finest level means the whole
        # download: by_county already delivers the localities
        if not implicit or len(teritoriale) > 1:
            return []
        return [implicit]

    def get(self, level: territory.Level | str | None = "finest",
            levels: list[territory.Level] | None = None,
            tidy: bool = True, progress="auto", raw: bool = False,
            confirm: bool = True):
        """The indicator's data, as a long format DataFrame.

        It executes the plan from the registry: read the strategy, run it,
        apply tidy.

        level='finest' (the default) takes the finest level the indicator
        actually reaches; for non territorial matrices it filters nothing.
        level=None asks for everything. A specific level is named as such,
        for example level='judet'.

        tidy=True adds the derived columns; raw=True returns exactly what INS
        returned. progress='auto' only speaks when the plan has more than one
        request. confirm=False skips the question before expensive downloads,
        for scripts.
        """
        self._ensure_meta()
        plan = self.fetch_plan()
        wanted = self._wanted_levels(level, levels, plan)
        selection = self._build_selection(wanted)
        planuri = chunking.plan_requests(self, selection)

        vorbeste = (len(planuri) > 1) if progress == "auto" else bool(progress)
        if progress is not False:
            print(f"{self.code}: {_decision_line(self, wanted, plan, planuri)}")
        if confirm and len(planuri) > POLITE_REQUESTS and not _ask_big(
                self.code, len(planuri)):
            raise ValueError(
                f"{self.code}: download cancelled. Try a level filter, or "
                f"get(confirm=False) if you are sure.")

        cadre = []
        for i, payload in enumerate(planuri, 1):
            cadre.append(parse.pivot_csv_to_dataframe(
                client.post_pivot(payload), self))
            if vorbeste:
                total = sum(len(c) for c in cadre)
                print(f"  {i}/{len(planuri)}: +{len(cadre[-1])} randuri "
                      f"(total {total})")

        df = cadre[0] if len(cadre) == 1 else pd.concat(cadre, ignore_index=True)
        return df if raw or not tidy else parse.standardize(df, self)

    def _repr_html_(self) -> str:
        """The card of a single indicator. Here the levels really are known.

        It does not fetch metadata by itself: a Matrix coming from search is
        shown with what it has, so displaying it in a notebook never triggers
        a GET.
        """
        rows = []
        if self.levels:
            rows.append(("nivele", ", ".join(self.levels)))
        if self.last_updated:
            rows.append(("actualizat", self.last_updated))
        if self.periodicity:
            rows.append(("periodicitate", ", ".join(self.periodicity)))
        if self.ancestors:
            rows.append(("unde", repr(self._breadcrumb())))
        meta = "".join(
            f"<tr><th align='left'>{html.escape(k)}</th>"
            f"<td>{html.escape(v)}</td></tr>" for k, v in rows
        )
        dims = "".join(
            f"<tr><td>{d.dim_index}</td><td>{html.escape(_clean(d.label))}</td>"
            f"<td>{html.escape(d.role)}</td><td>{len(d.options)}</td></tr>"
            for d in self.dimensions
        )
        out = [f"<p><code>{html.escape(self.code)}</code> "
               f"<b>{html.escape(_clean(self.name))}</b></p>"]
        if meta:
            out.append(f"<table><tbody>{meta}</tbody></table>")
        if dims:
            out.append(
                "<table><thead><tr><th>#</th><th>dimensiune</th><th>rol</th>"
                f"<th>optiuni</th></tr></thead><tbody>{dims}</tbody></table>")
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


def get(cod: str, level: territory.Level | None = None,
        levels: list[territory.Level] | None = None,
        tidy: bool = False, progress: bool = False):
    """Shortcut: one indicator's data, as a DataFrame."""
    return matrix(cod).get(level=level, levels=levels, tidy=tidy,
                           progress=progress)
