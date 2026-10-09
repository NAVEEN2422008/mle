#!/usr/bin/env python3
"""
BibTeX citation audit for paper/references.bib:
Verifies that every citation in paper/paper.tex resolves to a bib entry.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tex_path = ROOT / "paper" / "paper.tex"
bib_path = ROOT / "paper" / "references.bib"

if not tex_path.exists() or not bib_path.exists():
    print(f"[FAIL] Missing paper.tex or references.bib: tex={tex_path.exists()}, bib={bib_path.exists()}")
    sys.exit(1)

tex = tex_path.read_text(encoding="utf-8")
bib = bib_path.read_text(encoding="utf-8")

# Extract all citation keys from LaTeX
raw_citations = re.findall(r"\\cite[a-z]*\{([^}]+)\}", tex)
cited_keys = set()
for c in raw_citations:
    for k in c.split(","):
        k = k.strip()
        if k:
            cited_keys.add(k)

# Extract all keys defined in BibTeX
defined_keys = set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", bib))

missing_keys = cited_keys - defined_keys
unused_keys = defined_keys - cited_keys

print(f"cited keys   : {len(cited_keys)}")
print(f"bib entries  : {len(defined_keys)}")

if missing_keys:
    print(f"\n[FAIL] Cited keys missing from references.bib:")
    for k in sorted(missing_keys):
        print(f"  - {k}")
    sys.exit(1)

print("OK: every cited key resolves to a bib entry")
print(f"\ndefined but never cited: {len(unused_keys)}")
for k in sorted(unused_keys):
    print(f"  - {k}")

sys.exit(0)
