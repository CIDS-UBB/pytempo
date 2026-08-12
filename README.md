# pytempo

Bibliotecă Python pentru accesul la datele Institutului Național de Statistică,
via TEMPO Online. Un singur rol: vorbește frumos cu API-ul INS. Fără bază de date,
fără enrichment SIRUTA, fără loader Postgres. Astea trăiesc în proiecte separate,
în aval, care importă biblioteca asta.

Status: în lucru. Implementat acum (iterația 1): descoperirea (căutare + listă de
indicatori). Restul vine pe iterații, vezi SPEC.md.

## Instalare

Import-ul este `pytempo`. Instalezi direct din GitHub:

    pip install git+https://github.com/CIDS-UBB/pytempo.git

apoi:

    import pytempo as t

Notă despre PyPI: numele `pytempo` e deja ocupat acolo (o extensie Web3, fără
legătură), deci numele de distribuție e `pytempo-ins`. Instalarea din GitHub de mai
sus îți dă oricum `import pytempo`. Dacă vei publica pe PyPI, va fi `pip install
pytempo-ins`, tot cu `import pytempo`.

## Ce merge acum

    import pytempo as t

    t.load_index()                # lista întreagă de indicatori: [{code, name}, ...]
    t.name_dict()                 # dicționarul {cod: nume}
    t.search("FOM104D")           # caută după cod
    t.search("someri")            # caută după cuvânt (fără diacritice: prinde "Șomerii")

    for m in t.search("someri"):
        print(m.code, m.name, m.url, m.link_ok())

Verificare rapidă că linkurile răspund:

    python examples/check_links.py

## Vine mai târziu

    t.info(cod), t.matrix(cod).levels       metadate + nivele   (iterația 2)
    t.matrix(cod).get(level=...)            date, cu filtru      (iterația 3)
    t.init(), t.browse()                    explorare            (iterația 4)
    pytempo.schema.build_schema(m)          schemă Postgres      (iterația 5)

## Licență

MIT.
