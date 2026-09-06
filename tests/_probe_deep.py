"""Deep structural probe of logged-in PRADAN JSF app."""
import sys, re
sys.path.insert(0, ".")
from src.ingest.pradan_download import PradanSession, BASE

s = PradanSession.from_cred_file("PRADAN.cred")
assert s.login()
r = s.s.get(f"{BASE}/protected/payload.xhtml", timeout=60)
html = r.text

print("== ALL HREFS ==")
for h in sorted(set(re.findall(r'href="([^"]+)"', html)))[:40]:
    print("  ", h[:110])

print("\n== FORMS ==")
for f in re.findall(r'<form[^>]*>', html):
    print("  ", f[:150])

print("\n== JS/AJAX ENDPOINT HINTS ==")
for pat in (r'url\s*:\s*["\']([^"\']+)', r'action="([^"]+)"',
            r'src="([^"]+\.js[^"]*)"'):
    hits = sorted(set(re.findall(pat, html)))[:12]
    for h in hits:
        print("  ", h[:110])

print("\n== VIEWSTATE present:", "javax.faces.ViewState" in html,
      "| PrimeFaces:", "PrimeFaces" in html)

# Try known ISSDC alternate hosts/patterns anonymously & logged-in
probes = [
    "https://pradan.issdc.gov.in/al1",
    f"{BASE}/protected/download.xhtml",
    f"{BASE}/WEBDATA/",
    "https://astrobrowse.issdc.gov.in/astro_archive/archive/Home.jsp",
]
print("\n== EXTRA PROBES ==")
for u in probes:
    try:
        rr = s.s.get(u, timeout=40, allow_redirects=True)
        print(f"  {rr.status_code} len={len(rr.text):>7}  {u}")
    except Exception as e:
        print(f"  ERR {type(e).__name__} {u}")
