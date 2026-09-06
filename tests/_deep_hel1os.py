"""Deeper HEL1OS table inspection"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright

lines = [l.strip() for l in (Path("PRADAN.cred").read_text().splitlines()) if l.strip()]
user, pwd = lines[0], lines[1]

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    pg = b.new_context(accept_downloads=True).new_page()
    pg.goto("https://pradan1.issdc.gov.in/al1/", wait_until="networkidle", timeout=90000)
    pg.click("a:has-text('Login/Signup')", timeout=30000)
    pg.wait_for_load_state("networkidle", timeout=60000)
    if pg.locator("#username").count():
        pg.fill("#username", user); pg.fill("#password", pwd)
        pg.click("#kc-login"); pg.wait_for_load_state("networkidle", timeout=90000)

    pg.goto("https://pradan1.issdc.gov.in/al1/protected/browse.xhtml?id=hel1os", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(3000)

    for t in range(pg.locator("table").count()):
        rows = pg.locator("table").nth(t).locator("tr")
        n = rows.count()
        if n > 0:
            print(f"\ntable{t}: {n} rows")
            for r in range(min(n, 3)):
                print(f"  row{r}: {rows.nth(r).inner_text()[:200]}")