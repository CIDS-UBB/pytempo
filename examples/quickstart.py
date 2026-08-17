"""How pytempo is meant to be used, in one runnable file.

It makes a handful of real requests, so it needs access to statistici.insse.ro:

    python examples/quickstart.py

The guided tour is in the notebooks next to this file. This is the short
version, for reading rather than for learning.
"""
import pytempo as t

# 1. find an indicator. find is the plain keyword search, search takes filters
print(f"'salariati' matches {len(t.find('salariati'))} indicators")
print(f"{len(t.search(level='localitate'))} of the catalogue reach localities")

# 2. read one, and let it tell you how it wants to be downloaded
m = t.matrix("FOM101A")
m.what()
m.how()          # every level with its size and cost, every filter, a call

# 3. the data, tidied, at one level
df = m.get(level="judet", progress=False)
print("counties:", df.shape)

# 4. the fine territory by question, not by spelling: FOM104D calls it
#    'Localitati' and GOS102A calls it 'Municipii si orase'
towns = t.matrix("GOS102A")
columns = towns.territory_columns()
print("SIRUTA column here:", columns["siruta"])

# 5. filtering. A list, a predicate, or a word for a dimension with levels
ages = t.matrix("POP107D")
print("age groups:", len(ages.options("varsta", kind="groups")), "of",
      len(ages.options("varsta")))
by_county = ages.get(level="judet", select={"varsta": "groups"},
                     progress=False)
print("19 age groups by county:", by_county.shape)

# 6. a large indicator goes through disk: each request written as it arrives,
#    resumable, checked when the slices are joined. get() would stop and say so
#    df = ages.download(level="localitate", folder="data/pop107d")

# 7. before you trust it, check a couple of units against the site by hand
df.tempo.spot_check(1, seed=7)

# 8. the SQL to load it, as text. pytempo never connects to a database
print(m.schema()[:400], "...")
