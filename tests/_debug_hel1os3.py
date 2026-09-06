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

    # Set date filter for 2026-08-20
    dt_from_in = pg.locator("#filterForm\\:filterTable\\:0\\:datetime1_input")
    dt_to_in = pg.locator("#filterForm\\:filterTable\\:0\\:datetime2_input")
    filter_btn = pg.locator("#filterForm\\:filterButton")

    print("dt_from_in count:", dt_from_in.count())
    print("dt_to_in count:", dt_to_in.count())
    print("filter_btn count:", pg.locator("#filterForm\\:filterButton").count())

    if dt_from_in.count() and dt_to_in.count():
        dt_from_in.fill("00:00:00")
        dt_to_in.fill("23:59:59")
        pg.locator("#filterForm\\:filterButton").click()
        pg.wait_for_load_state("networkidle", timeout=30000)
        pg.wait_for_timeout(3000)
        print("Filter applied")

    # Check table
    table = pg.locator("table").nth(1)
    rows = pg.locator("table").nth(1).locator("tbody tr")
    count = rows.count()
    print(f"Row count after filter: {rows.count()}")
    for i in range(min(3, rows.count())):
        row = rows.nth(i)
        fname_el = row.locator("td:nth-child(3)")
        fname = fname_el.inner_text().strip()
        print(f"Row {i}: {fname[:100]}")
        
        # Check for View link
        view_links = row.locator("a")
        print(f"  Links in row: {view_links.count()}")
        for l_idx in range(view_links.count()):
            link = view_links.nth(l_idx)
            print(f"  Link {l_idx}: text='{view_links.nth(l_idx).inner_text()[:50]}', href='{view_links.nth(l_idx).get_attribute('href')}', onclick='{view_links.nth(l_idx).get_attribute('onclick')[:80]}'")