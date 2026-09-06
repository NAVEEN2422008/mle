import sys, re
sys.path.insert(0, ".")
from src.ingest.pradan_download import PradanSession, BASE

s = PradanSession.from_cred_file("PRADAN.cred")
assert s.login()
r = s.s.get(f"{BASE}/protected/payload.xhtml", timeout=60)
html = r.text
vs = re.search(r'javax\.faces\.ViewState"[^>]*value="([^"]+)"', html).group(1)

def click(idx):
    src = f"tableForm:payloads:{idx}:j_idt42"
    return s.s.post(f"{BASE}/protected/payload.xhtml", data={
        "javax.faces.partial.request": "true",
        "javax.faces.partial.event": "click",
        "javax.faces.behavior.event": "action",
        "javax.faces.partial.execute": "@this",
        "javax.faces.partial.render": "@none",
        "javax.faces.source": src,
        src: src,
        "tableForm": "tableForm",
        "j_id1:javax.faces.ViewState": vs,
    }, timeout=90, headers={"Faces-Request": "partial/ajax",
                            "X-Requested-With": "XMLHttpRequest"})

for idx in range(10):
    rr = click(idx)
    ups = re.findall(r'<update id="([^"]*)"><!\[CDATA\[(.*?)\]\]></update>',
                     rr.text, re.S)
    joined = " ".join(u[1] for u in ups)
    name = ""
    for pat, lab in ((r"SoLEXS|SLX", "SoLEXS"), (r"HEL1OS|HLD", "HEL1OS"),
                     (r"VELC", "VELC"), (r"SUIT", "SUIT"),
                     (r"ASPEX", "ASPEX"), (r"PAPA", "PAPA"),
                     (r"Magnet", "MAG"), (r"SPICE", "SPICE")):
        if re.search(pat, joined, re.I):
            name += lab + ","
    zips = re.findall(r'[\w./\-]*AL1_[\w.\-]*\.zip', joined)[:2]
    print(f"idx={idx}: len={len(joined):>7} payloads=[{name.strip(',')}] "
          f"zips={zips} updates={[u[0][:28] for u in ups][:4]}")
