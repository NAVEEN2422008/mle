"""Logged-in discovery of real PRADAN file URLs (no creds printed)."""
import sys, re
sys.path.insert(0, ".")
from src.ingest.pradan_download import PradanSession, BASE

s = PradanSession.from_cred_file("PRADAN.cred")
assert s.login(), "login failed"
print("[+] logged in")

# 1) What's on the main protected page? Find payload section links
r = s.s.get(f"{BASE}/protected/payload.xhtml", timeout=60)
links = re.findall(r'href="([^"]*)"[^>]*>([^<]{2,40})<', r.text)
interesting = [(h, t.strip()) for h, t in links
               if any(k in h.lower() + t.lower()
                      for k in ("slx", "hld", "solex", "hel1o", "payload",
                                "browse", "dataset", "product"))]
for h, t in interesting[:20]:
    print(f"  LINK {t:30s} -> {h[:90]}")

# 2) Try likely section pages directly
for cand in ("/protected/solexs.xhtml", "/protected/SLX.xhtml",
             "/protected/slx.xhtml", "/protected/hel1os.xhtml",
             "/protected/HLD.xhtml"):
    rr = s.s.get(f"{BASE}{cand}", timeout=60)
    marker = "OK " if rr.status_code == 200 and len(rr.text) > 3000 else "..."
    print(f"  {marker} GET {cand} -> {rr.status_code} len={len(rr.text)}")

# 3) Any .zip references anywhere on payload page?
zips = re.findall(r'["\']([^"\']*\.zip)["\']', r.text)
print("zip refs on payload page:", zips[:5] if zips else "none")
