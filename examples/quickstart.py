"""How pytempo is meant to be used.

Some of this is illustrative: fuzzy search and the Postgres schema are not
implemented yet.
"""
import pytempo as t

# 1. find indicators
rezultate = t.search("șomeri", fuzzy=True)
for m in rezultate:
    print(m.code, m.name, m.levels)

# 2. metadata
print(t.info("SOM101B"))

# 3. data, with and without a level filter
m = t.matrix("FOM104D")
print(m.levels)
df_tot = m.get()
df_loc = m.get(level="localitate")

# 4. a Postgres schema, straight from the metadata
from pytempo.schema import build_schema
print(build_schema(m).to_ddl("postgres"))
