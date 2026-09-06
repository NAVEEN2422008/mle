"""Map payloads rows -> names, then attempt one PrimeFaces ajax click."""
import sys, re
sys.path.insert(0, ".")
from src.ingest.pradan_download import PradanSession, BASE

s = PradanSession.from_cred_file("PRADAN.cred")
assert s.login()
r = s.s.get(f"{BASE}/protected/payload.xhtml", timeout=60)
html = r.text

# find each payloads:N block and nearby label text
for m in re.finditer(r'id="tableForm:payloads:(\d+):j_idt42"', html):
    idx = m.group(1)
    ctx = html[max(0, m.start()-100): m.end()+400]
    label = re.findall(r'>\s*([A-Za-z][A-Za-z0-9 \-]{2,25})\s*<', ctx)
    print(f"row {idx}: {label[:4]}")

vs = re.search(r'name="j_id\d+:javax\.faces\.ViewState"\s+id="[^"]*"\s+value="([^"]+)"', html)
if not vs:
    vs = re.search(r'javax\.faces\.ViewState"[^>]*value="([^"]+)"', html)
viewstate = vs.group(1) if vs else ""
print("\nViewState len:", len(viewstate))

# attempt ajax click on each row index, look for SoLEXS/HEL1OS in response
def ajax_click(idx):
    src = f"tableForm:payloads:{idx}:j_idt42"
    data = {
        "javax.faces.partial.request": "true",
        "javax.faces.partial.event": "click",
        "javax.faces.partial.execute": f"@this",
        "javax.faces.partial.render": "@none",
        "javax.faces.source": src,
        src: src,
        "tableForm": "tableForm",
        "j_id1:javax.faces.ViewState": viewstate,
    }
    rr = s.s.post(f"{BASE}/protected/payload.xhtml", data=data, timeout=90,
                  headers={"Faces-Request": "partial/ajax",
                           "X-Requested-With": "XMLHttpRequest"})
    return rr

for idx in range(10):
    rr = ajax_click(idx)
    body = rr.text
    tag = ("SoLEXS" if re.search(r"solexs|SLX", body, re.I) else
           "HEL1OS" if re.search(r"hel1os|HLD", body, re.I) else "")
    print(f"click {idx}: HTTP {rr.status_code} len={len(body)} "
          f"match={tag or '-'}")
