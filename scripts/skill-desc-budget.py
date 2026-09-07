import json, re, os, sys
root, mp_path, budget = sys.argv[1], sys.argv[2], int(sys.argv[3])
declared = []
try:
    mp = json.load(open(mp_path))
    for pl in mp.get("plugins", []):
        src = pl.get("source")
        path = src if isinstance(src, str) else (src or {}).get("path", "")
        declared.append((pl.get("name", "?"), str(path).lstrip("./")))
except Exception:
    pass

rows, total = [], 0
for name, rel in declared:
    d = os.path.join(root, rel, "skills")
    if not os.path.isdir(d):
        continue
    n = 0
    for sk in sorted(os.listdir(d)):
        f = os.path.join(d, sk, "SKILL.md")
        if not os.path.isfile(f):
            continue
        m = re.match(r"^---\n(.*?)\n---", open(f).read(), re.DOTALL)
        if not m:
            continue
        fm = m.group(1)
        desc = re.search(r"description:\s*(.*?)(?=\n[a-z_-]+:|\Z)", fm, re.DOTALL)
        nm = re.search(r"name:\s*(\S+)", fm)
        n += len(" ".join(desc.group(1).split())) if desc else 0
        n += len(nm.group(1)) if nm else 0
    if n:
        rows.append((n, name)); total += n

rows.sort(reverse=True)
print(total)
print(" ".join("%d:%s" % (c, n) for c, n in rows[:5]))
