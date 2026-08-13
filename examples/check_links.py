"""A live check: the indicator list loads, search works, links answer.

Run it on a machine with access to statistici.insse.ro:
    python examples/check_links.py
"""
import pytempo as t

# 1. the whole indicator list (the name dictionary)
index = t.load_index()
print(f"indicators in total: {len(index)}")

# 2. the {code: name} dictionary, a sample
nume = t.name_dict()
print("example FOM104D ->", nume.get("FOM104D"))

# 3. look up one specific indicator
for m in t.search("FOM104D"):
    print(f"  found: {m.code} | {m.name}")
    print(f"  link : {m.url}")
    print(f"  does the link work? {m.link_ok()}")

# 4. a keyword search, to see the list
print("\nresults for 'someri':")
for m in t.search("someri", limit=15):
    print(f"  {m.code:10} {m.name}")
