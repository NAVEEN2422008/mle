"""Static check of paper/paper.tex: every included figure must exist on disk,
every \\ref must have a matching \\label, and environments must balance."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tex = (ROOT / "paper" / "paper.tex").read_text(encoding="utf-8")
figs = ROOT / "paper" / "figures"

fail = []

# 1. every included figure exists (pdf for LaTeX)
inc = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex)
print(f"includegraphics targets: {len(inc)}")
for rel in inc:
    p = (ROOT / "paper" / rel)
    ok = p.exists()
    print(f"  {'OK ' if ok else 'MISSING'}  {rel}")
    if not ok:
        fail.append(f"missing figure {rel}")

# 2. no references to figures that were withdrawn
withdrawn = ["figure4_ablation", "figure5_feature_importance",
             "figure7_ml_comparison", "figure8_roc_reliability",
             "figure9_lt_far"]
for w in withdrawn:
    if w in tex:
        fail.append(f"withdrawn figure still referenced: {w}")
print(f"\nwithdrawn-figure references: {[w for w in withdrawn if w in tex] or 'none'}")

# 3. label / ref consistency
labels = set(re.findall(r"\\label\{([^}]+)\}", tex))
refs = set(re.findall(r"\\ref\{([^}]+)\}", tex))
missing = sorted(refs - labels)
print(f"\nlabels={len(labels)} refs={len(refs)}")
print(f"refs without a label: {missing or 'none'}")
if missing:
    fail.append(f"dangling refs: {missing}")

unused = sorted(labels - refs)
print(f"labels never referenced: {unused or 'none'}")

# 4. environment balance
for env in ("figure", "table", "itemize", "enumerate", "abstract", "document"):
    b = tex.count("\\begin{%s}" % env)
    e = tex.count("\\end{%s}" % env)
    status = "OK " if b == e else "BAD"
    print(f"  {status} {env:<10} begin={b} end={e}")
    if b != e:
        fail.append(f"unbalanced environment {env}: {b}/{e}")

# 5. brace balance
if tex.count("{") != tex.count("}"):
    fail.append("unbalanced braces")
print(f"\nbraces: {{={tex.count('{')} }}={tex.count('}')}")

print("\n" + "=" * 60)
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
else:
    print("paper.tex is internally consistent and all figures exist")
print("=" * 60)
raise SystemExit(1 if fail else 0)