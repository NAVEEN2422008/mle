"""Recon 2: enter SoLEXS via its folder icon; dump the file browser UI."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright

lines = [l.strip() for l in (ROOT / "PRADAN.cred").read_text(encoding="utf-8").splitlines() if l.strip()]
user, pwd = lines[0], lines[1]

with sync_playwright() as pw:
    try:
        b = pw.chromium.launch(channel="msedge", headless=True)
    except Exception:
        b = pw.chromium.launch(channel="chrome", headless=True)
    pg = b.new_context(accept_downloads=True).new_page()
    pg.goto("https://pradan1.issdc.gov.in/al1/", wait_until="networkidle", timeout=90000)
    pg.click("a:has-text('Login/Signup')", timeout=30000)
    pg.wait_for_load_state("networkidle", timeout=60000)
    if pg.locator("#username").count():
        pg.fill("#username", user); pg.fill("#password", pwd)
        pg.click("#kc-login"); pg.wait_for_load_state("networkidle", timeout=90000)

    # SoLEXS is the 3rd payload table (index 2). Click its folder-icon button.
    pg.locator("table").nth(2).locator("button, .ui-button, [role=button], a").first.click(timeout=20000)
    pg.wait_for_load_state("networkidle", timeout=60000)
    pg.wait_for_timeout(3000)

    print("URL:", pg.url[:100])
    print("TITLE:", pg.title())

    # inputs
    ins = pg.eval_on_selector_all(
        "input, select",
        """els => els.map(e => ({tag:e.tagName,id:e.id,name:e.name,type:e.type||'',
             ph:e.placeholder||'',val:(e.value||'').slice(0,25)}))""")
    print("\n[INPUTS/SELECTS]")
    for i in ins[:20]:
        print("  ", i)

    # buttons
    btns = pg.eval_on_selector_all(
        "button, .ui-button, [role=button], input[type=submit], a.ui-commandlink",
        "els => els.map(e => (e.innerText||e.value||e.id||'').trim()).filter(t=>t)")
    print("\n[BUTTONS]", sorted(set(btns))[:25])

    # tables / rows sample
    print("\n[TABLES]:", pg.locator("table").count())
    for t in range(min(pg.locator("table").count(), 4)):
        rows = pg.locator("table").nth(t).locator("tr")
        n = rows.count()
        head = rows.nth(0).inner_text()[:150].replace(chr(10), " | ") if n else ""
        print(f" table{t}: {n} rows | head: {head}")

    pg.screenshot(path=str(ROOT / "tests" / "_ui_solexs.png"), full_page=True)
    print("\nscreenshot: tests/_ui_solexs.png")
    b.close()
