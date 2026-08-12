"""Cum se va folosi pytempo (odată implementate iterațiile).

Rulează doar după ce iterațiile 1-3 sunt gata; acum e ilustrativ.
"""
import pytempo as t

# 1. caută indicatori
rezultate = t.search("șomeri", fuzzy=True)
for m in rezultate:
    print(m.code, m.name, m.levels)

# 2. metadate
print(t.info("SOM101B"))

# 3. date, cu și fără filtru pe nivel
m = t.matrix("FOM104D")
print(m.levels)
df_tot = m.get()
df_loc = m.get(level="localitate")

# 4. schema pentru Postgres, direct din metadate
from pytempo.schema import build_schema
print(build_schema(m).to_ddl("postgres"))
