import re
from pathlib import Path

text = Path("scripts/expand_treatise_prose.py").read_text(encoding="utf-8")
pattern = re.compile(r'<div class="([^"]*figure-container[^"]*)">.*?\{fig(\d+)\}', re.DOTALL)
for m in pattern.finditer(text):
    print(f"Fig {m.group(2):>2}: class='{m.group(1)}'")
