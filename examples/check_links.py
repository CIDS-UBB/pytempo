"""Test: lista de indicatori se încarcă, căutarea merge, linkurile răspund.

Rulează pe o mașină cu acces la statistici.insse.ro:
    python examples/check_links.py
"""
import pytempo as t

# 1. lista întreagă de indicatori (dicționarul de nume)
index = t.load_index()
print(f"indicatori în total: {len(index)}")

# 2. dicționarul {cod: nume}, un eșantion
nume = t.name_dict()
print("exemplu FOM104D ->", nume.get("FOM104D"))

# 3. caută un indicator specific
for m in t.search("FOM104D"):
    print(f"  găsit: {m.code} | {m.name}")
    print(f"  link : {m.url}")
    print(f"  merge linkul? {m.link_ok()}")

# 4. o căutare pe cuvânt, ca să vezi lista
print("\nrezultate pentru 'someri':")
for m in t.search("someri", limit=15):
    print(f"  {m.code:10} {m.name}")
