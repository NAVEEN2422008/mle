import sys, re
sys.path.insert(0, ".")
from src.ingest.pradan_download import PradanSession, BASE

s = PradanSession.from_cred_file("PRADAN.cred")
assert s.login()
r = s.s.get(f"{BASE}/protected/payload.xhtml", timeout=60)
html = r.text
vs = re.search(r'javax\.faces\.ViewState"[^>]*value="([^"]+)"', html).group(1)

# show raw body of a naive click (what were those 1190 bytes?)
def click(idx, extra=None):
    src = f"tableForm:payloads:{idx}:j_idt42"
    data = {
        "javax.faces.partial.request": "true",
        "javax.faces.partial.event": "click",
        "javax.faces.behavior.event": "action",
        "javax.faces.partial.execute": "@this",
        "javax.faces.partial.render": "@this",
        "javax.faces.source": src,
        src: src,
        "tableForm": "tableForm",
        "j_id1:javax.faces.ViewState": vs,
    }
    if extra:
        data.update(extra)
    rr = s.s.post(f"{BASE}/protected/payload.xhtml", data=data, timeout=90,
                  headers={"Faces-Request": "partial/ajax",
                           "X-Requested-With": "XMLHttpRequest"})
    return rr

rr = click(2)
print("== raw response idx=2 ==")
print(rr.text[:500])
print("...")
