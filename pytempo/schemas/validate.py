"""Validarea registrului cu date reale, pe felii mici.

O fișă de registry spune ce ar trebui să se întâmple. Validarea cere efectiv o
felie de câteva zeci de celule din fiecare indicator și verifică faptele:
CSV-ul se parsează, coloanele se potrivesc, valorile sunt numerice, SIRUTA iese
unde trebuie, iar o celulă aleasă la întâmplare are aceeași valoare când o ceri
singură.

Nimic de aici nu e API public. Se folosește din dezvoltare:
    from pytempo import schemas
    schemas.validate(sample=15, seed=42)
    schemas.validate()                    # tot catalogul, cu resume
    schemas.spot_check_list(5)
"""
import datetime
import random
import time

from .. import chunking, client, parse, territory
from ..matrix import matrix as fetch_matrix
from . import build
from .build import REGISTRY_VERSION, _save, load_registry

MIN_PER_FAMILY = 3


def _now() -> str:
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds")


def stratified_sample(entries: dict, n: int, seed=None) -> list[str]:
    """Eșantion aleatoriu, stratificat pe familii, minim MIN_PER_FAMILY.

    Proporțional cu mărimea familiei, dar cu un prag de jos: neteritorialul e
    71% din catalog, iar familiile mici ar dispărea complet dintr-un eșantion
    strict proporțional.
    """
    rnd = random.Random(seed)
    pe_familie = {}
    for cod, e in entries.items():
        if e.get("status") == "ok":
            pe_familie.setdefault(e.get("family", "alt"), []).append(cod)

    total = sum(len(v) for v in pe_familie.values())
    ales = []
    for fam, coduri in sorted(pe_familie.items()):
        cota = max(MIN_PER_FAMILY, round(n * len(coduri) / total)) if total else 0
        cota = min(cota, len(coduri))
        ales += rnd.sample(sorted(coduri), cota)
    rnd.shuffle(ales)
    return ales


def _year_option(dim):
    """Opțiunea celui mai recent an de pe o dimensiune de timp."""
    cu_an = [(parse._year_of(o.label), o) for o in dim.options]
    cu_an = [(an, o) for an, o in cu_an if an is not None]
    if cu_an:
        return max(cu_an, key=lambda pereche: pereche[0])[1]
    return dim.options[-1]


def _slice_for(m, entry: dict) -> list[list[int]]:
    """Selecția feliei mici de testat, per dimensiune, în ordinea din API.

    Ținta e un singur POST de zeci de celule, indiferent de familie.
    """
    familie = entry.get("family")
    terr = [d for d in m.dimensions if d.role == "teritoriu"]
    localitati = next((d for d in terr
                       if territory.is_locality_dimension(d, m.details)), None)
    judete = None
    if localitati is not None and len(terr) > 1:
        judete = max((d for d in terr if d is not localitati),
                     key=lambda d: len(d.options))

    # judetul pe care il testam: primul care nu e agregatul TOTAL
    judet_ales = None
    if judete is not None:
        judet_ales = next((o for o in judete.options
                           if o.label.strip().upper() != "TOTAL"), None)

    selectie = []
    for d in m.dimensions:
        if d.role == "timp":
            selectie.append([_year_option(d).nom_item_id])
        elif d is localitati and familie == "judet_localitate":
            if judet_ales is not None:
                grupuri = territory.group_localities_by_county(d)
                ids = [o.nom_item_id
                       for o in grupuri.get(judet_ales.nom_item_id, [])]
            else:
                ids = []
            # fara pereche judet plus localitate luam un cap de lista
            selectie.append(ids or [o.nom_item_id for o in d.options[:20]])
        elif d is judete and judet_ales is not None:
            selectie.append([judet_ales.nom_item_id])
        elif d.role == "teritoriu":
            selectie.append([o.nom_item_id for o in d.options])
        else:
            selectie.append([d.options[0].nom_item_id])
    return selectie


def _payload(m, selectie) -> dict:
    return {
        "language": "ro",
        "encQuery": chunking.build_encquery(selectie),
        "matCode": m.code,
        "matMaxDim": m.details.get("matMaxDim"),
        "matUMSpec": m.details.get("matUMSpec"),
    }


def _norm_label(text) -> str:
    """Etichetele din CSV vin fără virgulele din denumirea originală."""
    return " ".join(str(text).replace(",", " ").split()).lower()


def _point_check(m, df) -> str | None:
    """Cere o singură celulă din felie și compară valoarea. None dacă e bine."""
    rand = df.iloc[len(df) // 2]
    selectie = []
    for d in m.dimensions:
        eticheta = _norm_label(rand[d.label.strip()])
        gasit = next((o for o in d.options
                      if _norm_label(o.label) == eticheta), None)
        if gasit is None:
            return (f"nu pot mapa eticheta {rand[d.label.strip()]!r} "
                    f"inapoi la un cod pe dimensiunea {d.label.strip()!r}")
        selectie.append([gasit.nom_item_id])

    text = client.post_pivot(_payload(m, selectie))
    singur = parse.pivot_csv_to_dataframe(text, m)
    if len(singur) != 1:
        return f"celula punctuala a intors {len(singur)} randuri, asteptat 1"
    a, b = rand["Valoare"], singur.iloc[0]["Valoare"]
    if a != b:
        return f"celula punctuala difera: in felie {a}, ceruta singur {b}"
    return None


def _checks(m, entry, df) -> str | None:
    """Verificările pe felia primită. None dacă totul e în regulă."""
    if entry.get("has_siruta"):
        tidy = parse.standardize(df, m)
        loc = [d for d in m.dimensions
               if d.role == "teritoriu"
               and territory.is_locality_dimension(d, m.details)]
        for d in loc:
            coloana = tidy[f"{d.label.strip()}_siruta"]
            localitati = tidy[f"{d.label.strip()}_nivel"] == "localitate"
            if localitati.any() and coloana[localitati].isna().all():
                return (f"has_siruta True, dar SIRUTA iese gol pe toate "
                        f"localitatile din {d.label.strip()!r}")

    um = [d for d in m.dimensions if d.role == "um"]
    if any("persoane" in territory._norm(d.label) for d in um):
        negative = (df["Valoare"] < 0).sum()
        if negative:
            return f"{negative} valori negative unde UM e numar de persoane"

    return _point_check(m, df)


def validate(sample: int | None = None, resume: bool = True,
             progress: bool = True, delay: float = 1.0, seed=None,
             path=None) -> dict:
    """Cere o felie mică din fiecare indicator și verifică ce a venit.

    sample=N ia un eșantion stratificat pe familii; sample=None ia tot
    catalogul, pentru rularea lungă. resume sare peste ce a trecut deja la
    aceeași versiune de registry, deci rularea lungă poate fi oprită și reluată.
    """
    path = path or build.REGISTRY_PATH
    date = load_registry(path)
    if not date:
        print("Nu exista registry.json. Ruleaza schemas.build_registry().")
        return {}
    entries = date["entries"]

    if sample:
        coduri = stratified_sample(entries, sample, seed=seed)
    else:
        coduri = [c for c, e in entries.items() if e.get("status") == "ok"]
    if resume:
        coduri = [c for c in coduri
                  if not (entries[c].get("validation") == "ok"
                          and entries[c].get("validated_version")
                          == REGISTRY_VERSION)]

    total = len(coduri)
    pornit = time.time()
    for i, cod in enumerate(coduri, 1):
        e = entries[cod]
        try:
            m = fetch_matrix(cod)
            selectie = _slice_for(m, e)
            celule = chunking.cells(selectie)
            df = parse.pivot_csv_to_dataframe(
                client.post_pivot(_payload(m, selectie)), m)
            if df.empty:
                e["validation"] = "empty"
            else:
                motiv = _checks(m, e, df)
                e["validation"] = f"error: {motiv}" if motiv else "ok"
            e["slice_cells"] = celule
        except Exception as exc:
            e["validation"] = f"error: {type(exc).__name__}: {exc}"
            e["slice_cells"] = 0
        e["validated_at"] = _now()
        e["validated_version"] = REGISTRY_VERSION

        if progress:
            scurs = time.time() - pornit
            ramas = scurs / i * (total - i)
            print(f"\rvalidez: {i}/{total}, ramas ~{ramas / 60:.1f} min",
                  end="", flush=True)
        if delay and i < total:
            time.sleep(delay)
    if progress and total:
        print()

    _save(date, path)
    if progress:
        validation_report(date)
    return date


def validation_report(date: dict | None = None, path=None) -> None:
    """Raportul validării: câți ok, câți goi, ce a mers prost și unde."""
    date = date or load_registry(path)
    if not date:
        print("Nu exista registry.json.")
        return
    entries = date["entries"]
    validate_le = {c: e for c, e in entries.items() if e.get("validation")}

    ok = [c for c, e in validate_le.items() if e["validation"] == "ok"]
    goi = [c for c, e in validate_le.items() if e["validation"] == "empty"]
    erori = {c: e["validation"] for c, e in validate_le.items()
             if e["validation"].startswith("error:")}

    print(f"\nValidare: {len(validate_le)} indicatori verificati")
    print(f"  ok    : {len(ok)}")
    print(f"  empty : {len(goi)}" + (f"  {goi[:8]}" if goi else ""))
    print(f"  erori : {len(erori)}")
    for cod, motiv in erori.items():
        print(f"    {cod:10} {motiv[:110]}")

    fara_siruta = [c for c, e in entries.items()
                   if e.get("has_localities") and not e.get("has_siruta")]
    if fara_siruta:
        print("\nlocalitati fara SIRUTA (tidy scoate coloana _siruta goala):")
        for cod in fara_siruta:
            e = entries[cod]
            print(f"  {cod:10} {e.get('name', '')[:70]}")
            print(f"             validare: {e.get('validation', 'neverificat')}")


def spot_check_list(n: int = 10, seed=None, path=None) -> list[dict]:
    """Listă de celule de verificat CU OCHII pe site-ul INS.

    De ce manual: site-ul TEMPO și API-ul sunt același sistem, deci o
    comparație automată ar compara API-ul cu el însuși și ar trece mereu.
    Singura verificare independentă e omul care se uită pe site, iar treaba
    noastră e să îi dăm lista gata făcută.
    """
    date = load_registry(path)
    if not date:
        print("Nu exista registry.json.")
        return []
    ok = sorted(c for c, e in date["entries"].items()
                if e.get("validation") == "ok")
    if not ok:
        print("Niciun indicator validat ok. Ruleaza schemas.validate(...).")
        return []

    rnd = random.Random(seed)
    randuri = []
    for cod in rnd.sample(ok, min(n, len(ok))):
        e = date["entries"][cod]
        try:
            m = fetch_matrix(cod)
            df = parse.pivot_csv_to_dataframe(
                client.post_pivot(_payload(m, _slice_for(m, e))), m)
            if df.empty:
                continue
            rand = df.iloc[len(df) // 2]
            combinatie = {d.label.strip(): rand[d.label.strip()]
                          for d in m.dimensions}
            randuri.append({"code": cod, "name": e.get("name", ""),
                            "combination": combinatie,
                            "value": rand["Valoare"], "url": e.get("endpoint")})
        except Exception as exc:
            print(f"  {cod}: nu pot compune celula ({exc})")

    print(f"\nDe verificat manual pe site, {len(randuri)} celule:")
    for r in randuri:
        print(f"\n{r['code']}  {r['name'][:70]}")
        for eticheta, valoare in r["combination"].items():
            print(f"    {eticheta[:40]:42} {valoare}")
        print(f"    {'VALOAREA NOASTRA':42} {r['value']}")
        print(f"    {r['url']}")
    return randuri
