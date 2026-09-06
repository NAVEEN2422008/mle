import sys, re
sys.path.insert(0, ".")
from src.ingest.pradan_download import PradanSession, BASE

s = PradanSession.from_cred_file("PRADAN.cred")
assert s.login()
r = s.s.get(f"{BASE}/protected/payload.xhtml", timeout=60)
html = r.text

print("== INPUT IDS ==")
for m in sorted(set(re.findall(r'<(?:input|select|button)[^>]*id="([^"]+)"', html))):
    print("  ", m)

print("\n== SELECTS & first options ==")
for sel in re.findall(r'<select[^>]*id="([^"]+)"[^>]*>(.*?)</select>', html, re.S)[:6]:
    opts = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', sel[1])[:6]
    print(" SELECT", sel[0])
    for v, t in opts:
        print("    ", repr(v), "->", t.strip()[:40])

print("\n== BUTTON/COMMAND hints ==")
for m in re.findall(r'id="([^"]*(?:search|Search|submit|Submit|go|Go|view|View)[^"]*)"', html):
    print("  ", m)

print("\n== getFilename definition ==")
m = re.search(r"function\s+getFilename\s*\(([^)]*)\)\s*{(.{0,400})", html, re.S)
if m:
    print(m.group(0)[:450])

print("\n== files[] population ==")
for m in re.findall(r".{80}files\s*=.{120}", html)[:4]:
    print("  ", m.replace(chr(10), " ")[:200])
