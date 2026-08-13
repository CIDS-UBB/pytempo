"""Obiectul Matrix: identitate + metadate + (mai târziu) date.

Endpoint-ul e definit de cod: totul pornește din t.matrix('FOM104D').
Căutarea (catalog.search) întoarce Matrix cu code + name + url; metadatele
se aduc la cerere, datele la iterația 3.

Aici stau și tipurile de afișare (MatrixList, TextList), ca listele întoarse
de search, domains și related să se vadă ca tabel, nu ca dict brut.

Atenție la cost: numele din API conțin HTML incorporat, iar nivelele cer
metadatele fiecărui indicator. Afișarea NU aduce metadate de la sine; arată
nivelele doar pentru indicatorii deja încărcați.
"""
import html
import re
from dataclasses import dataclass, field

import pandas as pd

from . import chunking, client, endpoints, parse, territory
from .chunking import MAX_CELLS
from .models import Dimension, Node, Option

# peste atatea cereri intrebam intai, ca sa nu pornim din greseala o
# descarcare de zeci de minute
POLITE_REQUESTS = 50

_ANCHORS = re.compile(r"<a\b[^>]*>.*?</a>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_EMPTY = re.compile(r"\(\s*\)|\[\s*\]")


def _clean(text: str) -> str:
    """Curăță un nume venit din API, ca să fie citibil într-un breadcrumb.

    Numele de noduri conțin ancore <a href=...>text</a> spre comunicate de presă.
    Scoatem ancora cu tot cu textul ei, altfel breadcrumb-ul devine un paragraf.
    Rămân apoi paranteze goale și separatori orfani, care se curăță și ei.
    """
    if not text:
        return ""
    out = _TAGS.sub(" ", _ANCHORS.sub(" ", html.unescape(text)))
    out = _EMPTY.sub(" ", out)
    return " ".join(out.split()).strip(" ;,-")


def _decision_line(m, wanted, plan, planuri) -> str:
    """Ce s-a hotarat, intr-o linie, inainte de descarcare."""
    if wanted:
        nivel = ", ".join(wanted)
        coada = " (cel mai fin)" if nivel == plan.get("default_level") else ""
        bucata = f"nivel {nivel}{coada}"
    else:
        bucata = "toate nivelele" if m.levels else "fara filtru teritorial"
    strategie = plan.get("strategy", "single")
    cereri = f"{len(planuri)} cerere" if len(planuri) == 1 else \
        f"{len(planuri)} cereri"
    return f"{bucata}, {strategie}, {cereri}"


def _ask_big(cod: str, cereri: int) -> bool:
    print(f"{cod}: {cereri} de cereri, cateva minute bune.")
    try:
        return input("Continui? [d/N] ").strip().lower() in ("d", "da", "y",
                                                             "yes")
    except (EOFError, OSError):
        return False


class TextList(list):
    """Listă de stringuri care se afișează citibil (breadcrumb, opțiuni)."""

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
    """Rezultatele unei căutări sau ale unei liste de noduri, ca tabel.

    Ține fie Matrix, fie Node. Coloana de nivele apare doar dacă TOATE
    elementele le au deja, din index sau din metadate aduse, ca afișarea să nu
    coste niciodată un apel. Domeniile nu au nivele, deci o listă de domenii nu
    primește coloana.
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
            return "niciun rezultat"
        cu_nivele = self._shows_levels()
        rows = self._rows(cu_nivele)
        wcode = max(len(r[0]) for r in rows)
        out = []
        for row in rows:
            linie = f"{row[0]:<{wcode}}  {row[1][:90]}"
            if cu_nivele:
                linie += f"  [{row[2]}]"
            out.append(linie)
        out.append(f"({len(rows)} rezultate)")
        return "\n".join(out)

    def _repr_html_(self) -> str:
        if not self:
            return "<p>niciun rezultat</p>"
        cu_nivele = self._shows_levels()
        antet = "<th>cod</th><th>nume</th>" + ("<th>nivele</th>" if cu_nivele
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
            f"<p>{len(self)} rezultate</p>"
        )

    def recent(self, n: int = 15) -> "MatrixList":
        """Cele mai recent actualizate n elemente DIN ACEST SET.

        Aduce metadatele doar pentru elementele setului. Nu există un recent
        global peste tot catalogul: ar însemna mii de apeluri.
        """
        loaded = [matrix(it.code) if not it.last_updated else it
                  for it in self if isinstance(it, Matrix)]
        loaded.sort(key=lambda m: _as_date(m.last_updated), reverse=True)
        return MatrixList(loaded[:n])


def _as_date(stamp: str) -> tuple:
    """'20-11-2025' -> (2025, 11, 20), sortabil. Necunoscutul cade la coadă."""
    parts = (stamp or "").split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        d, m, y = parts
        return (int(y), int(m), int(d))
    return (0, 0, 0)


@dataclass
class Matrix:
    """Un indicator TEMPO. După search are code + name; restul se populează leneș."""
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
    ancestors: list = field(default_factory=list)  # [{name, code}] domeniu -> parinte
    # nivelele venite din indexul local, cand metadatele nu au fost aduse.
    # None inseamna necunoscut; lista goala inseamna stiut ca nu are niciunul
    cached_levels: list | None = None

    @property
    def url(self) -> str:
        """Linkul către metadatele acestui indicator (GET matrix/{cod})."""
        return endpoints.matrix(self.code)

    def link_ok(self) -> bool:
        """True dacă linkul indicatorului răspunde. Pentru testul de linkuri."""
        return client.url_ok(self.url)

    @property
    def levels(self) -> list[str]:
        """Nivelele teritoriale prezente, de la general la specific.

        Din metadate dacă sunt aduse, altfel din index, dacă search le-a pus.
        """
        if self.dimensions:
            return territory.levels_present(self.dimensions, self.details)
        return list(self.cached_levels or [])

    @property
    def levels_known(self) -> bool:
        """Nivelele sunt disponibile fără niciun apel de rețea?"""
        return bool(self.dimensions) or self.cached_levels is not None

    @property
    def has_siruta(self) -> bool:
        """True dacă denumirile de localitate poartă prefix SIRUTA."""
        return bool(self.details.get("matSiruta"))

    def info(self) -> dict:
        """Metadatele complete, ca dicționar."""
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
        """Aduce metadatele dacă nu sunt deja acolo (search întoarce doar cod + nume)."""
        if not self.dimensions and not self.ancestors:
            fresh = matrix(self.code)
            for f in fresh.__dataclass_fields__:
                setattr(self, f, getattr(fresh, f))
        return self

    def _breadcrumb(self) -> TextList:
        """Doar drumul prin domenii, de la domeniul de sus spre indicator."""
        self._ensure_meta()
        names = [_clean(a.get("name", "")) for a in self.ancestors]
        return TextList([n for n in names if n], sep=" > ", show=10)

    def what(self) -> None:
        """Esența indicatorului, în câteva rânduri. Fișa lungă e describe()."""
        self._ensure_meta()
        print(f"{self.code}  {_clean(self.name)}")
        definitie = (self.definition or "").strip()
        if definitie:
            prima = re.split(r"\.\s", definitie, maxsplit=1)[0].strip()
            print(f"  {prima}.")
        um = [_clean(d.label).split(":", 1)[-1].strip()
              for d in self.dimensions if d.role == "um"]
        if um:
            print(f"  unitate     : {', '.join(um)}")
        if self.periodicity:
            print(f"  periodicitate: {', '.join(self.periodicity)}")
        if self.last_updated:
            print(f"  actualizat  : {self.last_updated}")
        ani = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b",
                                    self.observations or "")))
        if ani:
            print(f"  atentie     : observatiile mentioneaza anii "
                  f"{', '.join(ani)}, deci pot fi rupturi de serie")
            print("                citeste-le cu .describe()")

    def where(self) -> None:
        """Unde stă indicatorul și ce acoperă: domeniu, teritoriu, ani."""
        self._ensure_meta()
        crumbs = self._breadcrumb()
        if crumbs:
            print(f"domeniu : {crumbs!r}")

        for d in self.dimensions:
            if d.role != "teritoriu":
                continue
            print(f"teritoriu: {_clean(d.label)} ({len(d.options)} optiuni)")
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
            print("teritoriu: niciunul, indicatorul nu e teritorial")
        else:
            print(f"SIRUTA  : {'da' if self.has_siruta else 'nu'}")

        for d in self.dimensions:
            if d.role != "timp":
                continue
            ani = [parse._year_of(o.label) for o in d.options]
            ani = [a for a in ani if a]
            interval = f"{min(ani)} pana in {max(ani)}" if ani else "necunoscut"
            print(f"timp    : {_clean(d.label)}, {len(d.options)} perioade, "
                  f"{interval}")

    def how(self) -> None:
        """Manualul de descărcare al acestui indicator, gata de copiat."""
        self._ensure_meta()
        plan = self.fetch_plan()
        strategie = plan.get("strategy", "single")
        cereri = plan.get("est_requests", 1)
        implicit = plan.get("default_level")

        print(f"Cum descarci {self.code}:")
        print(f"  m = t.matrix({self.code!r})")
        print(f"  df = m.get()          "
              f"{'nivel ' + implicit if implicit else 'fara filtru teritorial'}"
              f", curatat")
        teritoriale = [d for d in self.dimensions if d.role == "teritoriu"]
        if len(teritoriale) > 1:
            # filtrul pe nivel nu merge cand judetul si localitatea sunt
            # dimensiuni separate; nu propunem ce ar arunca eroare
            print("  (filtrul pe nivel nu se aplica aici: judetul si "
                  "localitatea sunt")
            print("   dimensiuni separate, iar get() le aduce oricum pe "
                  "amandoua)")
        elif not implicit:
            motiv = ("indicatorul nu e teritorial" if not teritoriale else
                     "denumirile teritoriale nu se incadreaza in nomenclator")
            print(f"  (filtrul pe nivel nu se aplica aici: {motiv},")
            print("   deci get() ia tot)")
        else:
            for nivel in self.levels:
                if nivel != implicit:
                    print(f"  m.get(level={nivel!r})")
            if self.levels:
                print("  m.get(level=None)     toate nivelele la un loc")
        print("  m.get(raw=True)       exact ce da INS, fara coloane derivate")
        print()
        print(f"  strategie: {strategie}, aproximativ {cereri} "
              f"{'cerere' if cereri == 1 else 'cereri'}")
        if cereri > POLITE_REQUESTS:
            print(f"  ATENTIE: peste {POLITE_REQUESTS} de cereri, dureaza. "
                  f"get() te intreaba intai;")
            print("  pune confirm=False daca rulezi dintr-un script.")
        elif cereri > 1:
            print("  se descarca in mai multe cereri si se concateneaza")

    def related(self, limit: int = 25) -> MatrixList:
        """Ceilalți indicatori din același nod-părinte."""
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
        """Rezolvă o dimensiune după index, rol sau label."""
        if isinstance(dimension, int):
            return self.dimensions[dimension]

        want = _clean(str(dimension)).lower()
        terr = [d for d in self.dimensions if d.role == "teritoriu"]
        # 'teritoriu' da cea mai fina dimensiune teritoriala prezenta
        if want == "teritoriu" and terr:
            fine = [d for d in terr
                    if "localitate" in territory.dimension_levels(d, self.details)]
            return (fine or terr)[0]
        # un nivel ('judet', 'localitate', ...) da dimensiunea care il acopera
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
        raise ValueError(f"dimensiune necunoscuta: {dimension!r}. Disponibile: {avem}")

    def options(self, dimension=None, limit: int | None = None) -> TextList:
        """Denumirile opțiunilor unei dimensiuni, ca să știi ce poți filtra.

        Fără argument, listează dimensiunile indicatorului, cu rolul și câte
        opțiuni are fiecare, ca să vezi ce poți cere.

        dimension acceptă indexul, rolul ('timp', 'judet', 'teritoriu') sau
        labelul ('Judete'). limit taie lista întoarsă.
        """
        self._ensure_meta()
        if dimension is None:
            return TextList(
                [f"[{d.dim_index}] {_clean(d.label)} ({d.role}, "
                 f"{len(d.options)} optiuni)" for d in self.dimensions],
                sep="\n", show=50)

        dim = self._find_dimension(dimension)
        labels = [o.label for o in dim.options]
        if limit is not None:
            labels = labels[:limit]
        return TextList(labels)

    def show(self) -> None:
        """Rezumatul indicatorului, citibil: unde e, ce nivele, ce dimensiuni."""
        self._ensure_meta()
        print(f"{self.code}  {_clean(self.name)}")
        crumbs = self._breadcrumb()
        if crumbs:
            print(f"  unde      : {crumbs!r}")
        if self.levels:
            print(f"  nivele    : {', '.join(self.levels)}")
        if self.last_updated:
            print(f"  actualizat: {self.last_updated}")
        if self.periodicity:
            print(f"  periodic  : {', '.join(self.periodicity)}")
        print("  dimensiuni:")
        for d in self.dimensions:
            print(f"    [{d.dim_index}] {_clean(d.label)} ({d.role}, "
                  f"{len(d.options)} optiuni)")

    def describe(self) -> None:
        """Fișa completă a indicatorului, cu tot textul de la INS, netăiat.

        show() e rezumatul scurt și nu atinge textele. Aici se citește tot:
        definiția, metodologia, sursele și observațiile, unde stau notele de
        rupturi de serie și avertismentele despre ani incompleți.
        """
        self._ensure_meta()
        print(f"{self.code}  {_clean(self.name)}")
        crumbs = self._breadcrumb()
        if crumbs:
            print(f"domeniu     : {crumbs!r}")
        if self.levels:
            print(f"nivele      : {', '.join(self.levels)}")
        if self.periodicity:
            print(f"periodicitate: {', '.join(self.periodicity)}")
        if self.last_updated:
            print(f"actualizat  : {self.last_updated}")

        for titlu, text in (("DEFINITIE", self.definition),
                            ("METODOLOGIE", self.methodology)):
            if text and text.strip():
                print(f"\n{titlu}\n{text.strip()}")

        if self.sources:
            print("\nSURSE")
            for s in self.sources:
                nume = s.get("nume") if isinstance(s, dict) else str(s)
                # fara _clean aici: numele sursei poarta markerul INS <<6263>>,
                # pe care curatarea de HTML l-ar manca
                if nume and nume.strip():
                    print(f"  {nume.strip()}")

        if self.observations and self.observations.strip():
            print(f"\nOBSERVATII\n{self.observations.strip()}")

    def help(self) -> None:
        """Ce poți face cu un indicator."""
        print(f"""Indicatorul {self.code}. Ce poti face cu el:

  .show()              rezumat scurt: domeniu, nivele, dimensiuni
  .describe()          fisa completa: definitie, metodologie, surse, observatii
  .info()              aceleasi metadate, ca dictionar
  .where()             breadcrumb-ul de domeniu
  .related()           ceilalti indicatori din acelasi nod
  .levels              nivele, ex. ['national', 'judet', 'localitate']
  .has_siruta          True daca localitatile poarta prefix SIRUTA
  .options()           ce dimensiuni are, cu rol si numar de optiuni
  .options('teritoriu') ce valori are o dimensiune (index, rol sau label)
  .get()               datele, ca DataFrame in format lung
  .get(level='judet')  doar un nivel teritorial
  .get(tidy=True)      plus coloane derivate: SIRUTA, nivel, tip, an
  .get(progress=True)  spune cat s-a tras, la matricele mari""")

    def _build_selection(self, wanted: list[str]) -> list[list[int]]:
        """nomItemId-urile de trimis, per dimensiune, în ordinea din dimensionsMap.

        Fără nivele cerute, ia tot. Cu nivele cerute, taie doar dimensiunea
        teritorială; restul rămân complete.
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
        """Planul de extragere: din registry dacă e acolo, altfel calculat.

        Registrul vine cu pachetul, deci în mod normal planul e deja scris.
        Fallback-ul ține biblioteca funcțională fără registru.
        """
        from . import schemas  # local: schemas importa matrix, altfel ciclu

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
        """Nivelele cerute efectiv, după rezolvarea lui 'finest'.

        O listă explicită în levels bate implicitul: cine scrie
        levels=['judet', 'regiune'] a spus deja ce vrea.
        """
        explicite = list(levels or [])
        if isinstance(level, str) and level != "finest":
            explicite = [level] + explicite
        if explicite:
            return explicite
        if level != "finest":
            return []               # level=None cere tot

        implicit = plan.get("default_level")
        teritoriale = [d for d in self.dimensions if d.role == "teritoriu"]
        # la judet plus localitate, cel mai fin nivel inseamna descarcarea
        # intreaga: by_county livreaza chiar localitatile
        if not implicit or len(teritoriale) > 1:
            return []
        return [implicit]

    def get(self, level: territory.Level | str | None = "finest",
            levels: list[territory.Level] | None = None,
            tidy: bool = True, progress="auto", raw: bool = False,
            confirm: bool = True):
        """Datele indicatorului, ca DataFrame în format lung.

        Execută planul din registry: citește strategia, o rulează, aplică tidy.

        level='finest' (implicit) ia nivelul cel mai fin pe care îl are
        indicatorul; la matricele neteritoriale nu filtrează nimic. level=None
        cere tot. Un nivel anume se cere ca atare, ex. level='judet'.

        tidy=True adaugă coloanele derivate; raw=True dă exact ce a dat INS.
        progress='auto' vorbește doar când planul are mai multe cereri.
        confirm=False taie întrebarea de la descărcările scumpe, pentru
        scripturi.
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
                f"{self.code}: descarcare anulata. Incearca un filtru pe "
                f"nivel, sau get(confirm=False) daca esti sigur.")

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
        """Cardul unui singur indicator. Aici nivelele chiar sunt disponibile.

        Nu aduce metadate de la sine: un Matrix venit din search se afișează cu
        ce are, ca simpla afișare într-un notebook să nu declanșeze un GET.
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
    """Construiește un Matrix din JSON-ul brut al endpointului matrix/{cod}.

    Ordinea dimensiunilor din dimensionsMap se păstrează în dim_index: ea
    contează pentru ordinea din encQuery (iterația 3).
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
    """Construiește un Matrix aducând metadatele (GET matrix/{cod}).

    Verifică întâi codul în catalog, care e cache-uit: pentru un cod inexistent
    INS întoarce non-JSON, iar mesajul brut nu ajută pe nimeni.
    refresh=True ocolește cache-ul de metadate.
    """
    from . import catalog  # local: catalog importa matrix, altfel ciclu

    cod = (cod or "").strip().upper()
    if cod not in catalog.name_dict():
        raise ValueError(
            f"Codul '{cod}' nu exista in TEMPO. Cauta cu t.find(...).")
    data = client.get_json(endpoints.matrix(cod), use_cache=not refresh)
    return _build(cod, data)


def info(cod: str) -> dict:
    """Scurtătură: metadatele unui indicator."""
    return matrix(cod).info()


def get(cod: str, level: territory.Level | None = None,
        levels: list[territory.Level] | None = None,
        tidy: bool = False, progress: bool = False):
    """Scurtătură: datele unui indicator, ca DataFrame."""
    return matrix(cod).get(level=level, levels=levels, tidy=tidy,
                           progress=progress)
