"""UI recon: what does payload.xhtml actually look like after clicking SoLEXS?"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

lines = [l.strip() for l in (ROOT / "PRADAN.cred").read_text().splitlines() if l.strip()]
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
    print("URL:", pg.url[:80])

    # All clickable texts on payload page BEFORE click
    labels = pg.eval_on_selector_all(
        "button, .ui-button, [role='button'], a",
        "els => els.map(e => e.innerText.trim()).filter(t => t && t.length < 30)")
    print("\n[BUTTON/LINK TEXTS]", sorted(set(labels)))

    # Try clicking text 'SoLEXS' anywhere
    tgt = pg.locator("text=SoLEXS").first
    print("\n'SoLEXS' matches:", pg.locator("text=SoLEXS").count())
    if tgt.count():
        tgt.click(timeout=15000)
        pg.wait_for_timeout(4000)

    after = pg.eval_on_selector_all(
        "button, .ui-button, [role='button']",
        "els => els.map(e => e.innerText.trim()).filter(t => t && t.length<30)")
    print("[AFTER CLICK BUTTONS]", sorted(set(after)))

    # tables?
    print("\n[TABLES]:", pg.locator("table").count())
    for t in range(min(pg.locator("table").count(), 3)):
        rows = pg.locator("table").nth(t).locator("tr")
        print(f" table{t}: {rows.count()} rows; first row:",
              rows.nth(0).inner_text()[:120].replace(chr(10), " | ") if rows.count() else "")

    # inputs
    print("\n[INPUTS]")
    ins = pg.eval_on_selector_all(
        "input", """els => els.map(e => ({id:e.id,name:e.name,type:e.type,
                     ph:e.placeholder,val:(e.value||'').slice(0,20)}))""")
    for i in ins[:15]:
        print("  ", i)

    pg.screenshot(path=str(ROOT / "tests" / "_ui_after.png"), full_page=True)
    print("\nscreenshot saved tests/_ui_after.png")
    b.close()
