import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from pathlib import Path

lines = [l.strip() for l in (Path(__file__).resolve().parents[1] / "PRADAN.cred").read_text().splitlines() if l.strip()]
user, pwd = lines[0], lines[1]

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    pg = b.new_context(accept_downloads=True).new_page()
    pg.goto("https://pradan1.issdc.gov.in/al1/", wait_until="networkidle", timeout=90000)
    pg.click("a:has-text('Login/Signup')", timeout=30000)
    pg.wait_for_load_state("networkidle", timeout=60000)
    if pg.locator("#username").count():
        pg.fill("#username", user)
        pg.fill("#password", pwd)
        pg.click("#kc-login")
        pg.wait_for_load_state("networkidle", timeout=90000)

    pg.goto("https://pradan1.issdc.gov.in/al1/protected/browse.xhtml?id=hel1os", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(3000)

    # Check the table structure in detail
    table = pg.locator("table").nth(1)
    rows = pg.locator("table").nth(1).locator("tr")
    print(f"Total rows: {rows.count()}")
    
    for i in range(min(rows.count(), 3)):
        row = pg.locator("tbody tr").nth(i)
        print(f"\nRow {i}:")
        cells = row.locator("td")
        print(f"  Cell count: {cells.count()}")
        for c in range(cells.count()):
            cell = cells.nth(c)
            text = cell.inner_text()[:100]
            print(f"  Cell {c}: {text[:80]}")
            # Check for links in this cell
            links = cell.locator("a")
            if links.count() > 0:
                for l_idx in range(links.count()):
                    link = links.nth(l_idx)
                    print(f"  Link {l_idx}: text='{link.inner_text()[:50]}', href='{links.nth(l_idx).get_attribute('href')}', onclick='{links.nth(l_idx).get_attribute('onclick')[:50]}'")
        
        # Also check all links in the row
        links = row.locator("a")
        print(f"  Total links in row: {links.count()}")
        for l_idx in range(min(links.count(), 3)):
            link = links.nth(l_idx)
            print(f"  Link {l_idx}: text='{link.inner_text()[:50]}', href='{link.get_attribute('href')[:80]}', onclick='{link.get_attribute('onclick')[:50] if link.get_attribute('onclick') else 'None'}")

# Also check the actual HTML structure of a row
if pg.locator("tbody tr").count() > 0:
    row_html = pg.locator("tbody tr").first.inner_html()
    print("\nFirst row HTML (first 2000 chars):")
    print(row_html[:2000])