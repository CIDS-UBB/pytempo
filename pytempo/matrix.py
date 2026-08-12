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

from . import chunking, client, endpoints, parse, territory
from .models import Dimension, Node, Option

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

    Ține fie Matrix, fie Node. Arată doar cod și nume: domeniile nu au nivele,
    iar pentru indicatori nivelele cer metadatele fiecăruia, adică un apel per
    rând. Nivelele se văd pe cardul unui singur indicator, unde chiar le avem.
    """

    def _rows(self) -> list[tuple]:
        return [(it.code, _clean(it.name)) for it in self]

    def __repr__(self) -> str:
        if not self:
            return "niciun rezultat"
        rows = self._rows()
        wcode = max(len(r[0]) for r in rows)
        out = [f"{code:<{wcode}}  {name[:90]}" for code, name in rows]
        out.append(f"({len(rows)} rezultate)")
        return "\n".join(out)

    def _repr_html_(self) -> str:
        if not self:
            return "<p>niciun rezultat</p>"
        cells = "".join(
            f"<tr><td><code>{html.escape(c)}</code></td>"
            f"<td>{html.escape(n)}</td></tr>"
            for c, n in self._rows()
        )
        return (
            "<table><thead><tr><th>cod</th><th>nume</th></tr>"
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

    @property
    def url(self) -> str:
        """Linkul către metadatele acestui indicator (GET matrix/{cod})."""
        return endpoints.matrix(self.code)

    def link_ok(self) -> bool:
        """True dacă linkul indicatorului răspunde. Pentru testul de linkuri."""
        return client.url_ok(self.url)

    @property
    def levels(self) -> list[str]:
        """Nivelele teritoriale prezente, de la general la specific."""
        return territory.levels_present(self.dimensions, self.details)

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

    def where(self) -> TextList:
        """Breadcrumb-ul de domeniu, de la domeniul de sus spre indicator."""
        self._ensure_meta()
        names = [_clean(a.get("name", "")) for a in self.ancestors]
        return TextList([n for n in names if n], sep=" > ", show=10)

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

    def options(self, dimension, limit: int | None = None) -> TextList:
        """Denumirile opțiunilor unei dimensiuni, ca să știi ce poți filtra.

        dimension acceptă indexul, rolul ('timp', 'judet', 'teritoriu') sau
        labelul ('Judete'). limit taie lista întoarsă.
        """
        self._ensure_meta()
        dim = self._find_dimension(dimension)
        labels = [o.label for o in dim.options]
        if limit is not None:
            labels = labels[:limit]
        return TextList(labels)

    def show(self) -> None:
        """Rezumatul indicatorului, citibil: unde e, ce nivele, ce dimensiuni."""
        self._ensure_meta()
        print(f"{self.code}  {_clean(self.name)}")
        crumbs = self.where()
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

    def help(self) -> None:
        """Ce poți face cu un indicator."""
        print(f"""Indicatorul {self.code}. Ce poti face cu el:

  .show()              rezumat citibil: domeniu, nivele, dimensiuni
  .info()              aceleasi metadate, ca dictionar
  .where()             breadcrumb-ul de domeniu
  .related()           ceilalti indicatori din acelasi nod
  .levels              nivele, ex. ['national', 'judet', 'localitate']
  .has_siruta          True daca localitatile poarta prefix SIRUTA
  .options('teritoriu') ce valori are o dimensiune (index, rol sau label)
  .get()               datele, ca DataFrame in format lung""")

    def get(self, level: str | None = None, levels: list[str] | None = None):
        """Datele indicatorului, ca DataFrame în format lung.

        Ia toate opțiunile fiecărei dimensiuni, într-un singur POST la pivot.
        TODO 3b: level și levels sunt acceptați dar ignorați deocamdată, la fel
        chunking-ul pentru matricele care nu încap într-o singură cerere.
        """
        self._ensure_meta()
        selection = [[o.nom_item_id for o in d.options] for d in self.dimensions]
        payload = {
            "language": "ro",
            "encQuery": chunking.build_encquery(selection),
            "matCode": self.code,
            "matMaxDim": self.details.get("matMaxDim"),
            "matUMSpec": self.details.get("matUMSpec"),
        }
        return parse.pivot_csv_to_dataframe(client.post_pivot(payload), self)

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
            rows.append(("unde", repr(self.where())))
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


def matrix(cod: str) -> Matrix:
    """Construiește un Matrix aducând metadatele (GET matrix/{cod}).

    Verifică întâi codul în catalog, care e cache-uit: pentru un cod inexistent
    INS întoarce non-JSON, iar mesajul brut nu ajută pe nimeni.
    """
    from . import catalog  # local: catalog importa matrix, altfel ciclu

    cod = (cod or "").strip().upper()
    if cod not in catalog.name_dict():
        raise ValueError(
            f"Codul '{cod}' nu exista in TEMPO. Cauta cu t.find(...).")
    return _build(cod, client.get_json(endpoints.matrix(cod)))


def info(cod: str) -> dict:
    """Scurtătură: metadatele unui indicator."""
    return matrix(cod).info()


def get(cod: str, level: str | None = None, levels: list[str] | None = None):
    """Scurtătură: datele unui indicator, ca DataFrame."""
    return matrix(cod).get(level=level, levels=levels)
