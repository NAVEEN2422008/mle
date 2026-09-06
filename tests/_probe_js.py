import sys, re
sys.path.insert(0, ".")
from src.ingest.pradan_download import PradanSession, BASE

s = PradanSession.from_cred_file("PRADAN.cred")
assert s.login()

js = s.s.get(f"{BASE}/javax.faces.resource/pradan.js.xhtml?ln=scripts",
             timeout=60).text
print("pradan.js length:", len(js))

# hunt for endpoint-ish strings
pats = [
    r'["\']([^"\']*(?:download|Download|zip|ZIP|file|File|servlet|service|api|list)[^"\']*)["\']',
]
seen = set()
for pat in pats:
    for h in re.findall(pat, js):
        if h not in seen and len(h) < 120:
            seen.add(h)
            print("  ", h)

print("\n=== inline scripts on payload page ===")
r = s.s.get(f"{BASE}/protected/payload.xhtml", timeout=60)
inline = re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", r.text, re.S)
blob = "\n".join(inline)
for m in sorted(set(re.findall(
        r'["\']([^"\']*(?:download|zip|xhtml\?|servlet|getFile|fileName)[^"\']*)["\']',
        blob, re.I))):
    print("  ", m[:130])
