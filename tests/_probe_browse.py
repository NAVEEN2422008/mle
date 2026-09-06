"""Check if AL1Browse exposes SoLEXS/HEL1OS files publicly."""
import sys, re
sys.path.insert(0, ".")
import requests

UA = {"User-Agent": "Mozilla/5.0"}
s = requests.Session(); s.headers.update(UA)

r = s.get("https://pradan1.issdc.gov.in/al1/index.xhtml", timeout=60)
print("AL1Browse page:", r.status_code, "len", len(r.text))

# links & frames
for h in sorted(set(re.findall(r'(?:href|src)="([^"]+)"', r.text)))[:30]:
    print("  ", h[:110])

# look for data-browse hints
for kw in ("browse", "Browse", "SLX", "HLD", "SoLEXS", "HEL1OS",
           "archive", "data/", "WEBDATA"):
    print(f"  {kw}: {'YES' if kw in r.text else 'no'}")
