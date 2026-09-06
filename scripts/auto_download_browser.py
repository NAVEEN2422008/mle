"""Browser-automated PRADAN download v5 - robust, jump-to-file strategy.

Verified UI facts (from live recon):
- SoLEXS browser: /al1/protected/browse.xhtml?id=solexs  (HEL1OS: id=hel1os)
- SoLEXS filenames: AL1_SLX_L1_YYYYMMDD_v1.0.zip (direct download links)
- HEL1OS filenames: HLS_YYYYMMDD_HHMMSS_xxxxxxsec_lev1_V111.zip (direct download links)
- HEL1OS table: table1 (index 1), 11 rows (1 header + 10 data), 7 columns
  - Cell 0: row number (with link for preview)
  - Cell 1: preview link
  - Cell 2: filename
  - Cell 3: start time
  - Cell 4: end time
  - Cell 5: file size
  - Cell 6: Info (View link with onclick)
- Jump-to-File box (tableForm:j_idt187 + Submit) repositions the table so the
  target row is on page 1 -> click the link -> expect_download saves it.
- Latest release lags ~2-3 days; some days have gaps (e.g. Aug 16 2026).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "https://pradan1.issdc.gov.in/al1"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


def daterange(start: str, end: str):
    d0 = datetime.strptime(start, "%Y%m%d")
    d1 = datetime.strptime(end, "%Y%m%d")
    while d0 <= d1:
        yield d0.strftime("%Y%m%d")
        d0 += timedelta(days=1)


def harvest_solexs(page, days: list[str], raw: Path) -> tuple[int, list[str]]:
    """Download SoLEXS files using jump-to-file strategy."""
    got, missing = 0, []
    url = f"{BASE}/protected/browse.xhtml?id=solexs"

    for day in days:
        fname = f"AL1_SLX_L1_{day}_v1.0.zip"
        out = raw / fname
        if out.exists() and out.stat().st_size > 1000:
            got += 1
            continue
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(1200)

            # 1) link already on page 1? (recent dates sort to top)
            link = page.locator(f"a:has-text('{fname}')").first
            if not link.count():
                # 2) Jump-to-File reposition, then re-look
                jump = page.locator("input[placeholder='Filename']")
                if jump.count():
                    jump.fill(fname)
                    sub = page.locator(
                        "button:has-text('Submit'), input[value='Submit'], "
                        "a:has-text('Submit'), span:has-text('Submit')").first
                    sub.click(timeout=15000)
                    page.wait_for_timeout(2500)
                link = page.locator(f"a:has-text('{fname}')").first
            if not link.count():
                missing.append(fname)
                print(f"  [--] not on portal: {fname}")
                continue

            with page.expect_download(timeout=180000) as dl_info:
                link.click()
            dl = dl_info.value
            tmp = Path(dl.path())
            shutil.move(str(tmp), out)
            got += 1
            print(f"  [OK] {fname} ({out.stat().st_size // 1024} KB)")
        except Exception as e:
            missing.append(fname)
            print(f"  [--] {fname}: {type(e).__name__} {str(e)[:80]}")
    return got, missing


def harvest_hel1os(page, days: list[str], raw: Path) -> tuple[int, list[str]]:
    """Download HEL1OS files using date filter and pagination."""
    got, missing = 0, []
    url = f"{BASE}/protected/browse.xhtml?id=hel1os"

    for day in days:
        try:
            page.goto(f"{BASE}/protected/browse.xhtml?id=hel1os",
                      wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(1500)

            # Set date range filter: from 00:00:00 to 23:59:59 of the day
            date_str = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
            dt_from = f"{date_str} 00:00:00"
            dt_to = f"{date_str} 23:59:59"

            dt_from_in = page.locator("#filterForm\\:filterTable\\:0\\:datetime1_input")
            dt_to_in = page.locator("#filterForm\\:filterTable\\:0\\:datetime2_input")
            filter_btn = page.locator("#filterForm\\:filterButton")

            if dt_from_in.count() and dt_to_in.count():
                dt_from_in.fill("00:00:00")
                dt_to_in.fill("23:59:59")
                page.locator("#filterForm\\:filterButton").click()
                page.wait_for_load_state("networkidle", timeout=30000)
                page.wait_for_timeout(2000)

            downloaded = False
            max_pages = 5  # safety limit
            
            for page_num in range(5):  # max 5 pages
                # Find matching rows in the table (table1 has the data rows)
                table = page.locator("table").nth(1)  # table1 has the data rows
                rows = table.locator("tbody tr")
                count = rows.count()
                
                if count == 0:
                    break
                
                downloaded = False
                for i in range(count):
                    row = rows.nth(i)
                    fname_el = row.locator("td:nth-child(3)")  # Filename column (3rd column, 0-indexed = 2)
                    fname = fname_el.inner_text().strip()
                    if fname.startswith("HLS_") and day in fname:
                        # Find the View link - it's in the last column (cell 6)
                        link = row.locator("td:nth-child(7) a:has-text('View')").first
                        if not link.count():
                            # Try finding any link in the last column
                            link = row.locator("td:nth-child(7) a").first
                        if not link.count():
                            # Try any link in the row
                            link = row.locator("a:has-text('View')").first
                        if not link.count():
                            # Try any link with onclick
                            link = row.locator("a[onclick*='download'], a[onclick*='View']").first
                        
                        if link.count():
                            with page.expect_download(timeout=180000) as dl_info:
                                link.click()
                            dl = dl_info.value
                            tmp = Path(dl.path())
                            out = raw / fname
                            shutil.move(str(tmp), out)
                            got += 1
                            downloaded = True
                            print(f"  [OK] {fname} ({out.stat().st_size // 1024} KB)")
                            break
                
                if downloaded:
                    break
                
                # Check if there's a next page button
                next_btn = page.locator("a:has-text('Next'), a:has-text('Next'), .ui-paginator-next").first
                if next_btn.count():
                    next_btn.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    page.wait_for_timeout(2000)
                    continue
                else:
                    break
            else:
                missing.append(day)
                print(f"  [--] {day}: no matching file found")
                continue
        except Exception as e:
            missing.append(day)
            print(f"  [--] {day}: {type(e).__name__} {str(e)[:80]}")
    return got, missing


def harvest_tag(page, tag: str, days: list[str], raw: Path) -> tuple[int, list[str]]:
    if tag == "SLX":
        return harvest_solexs(page, days, raw)
    else:
        return harvest_hel1os(page, days, raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--creds", default="PRADAN.cred")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--instruments", default="both",
                    choices=["both", "solexs", "hel1os"])
    ap.add_argument("--forget", action="store_true")
    args = ap.parse_args()

    lines = [l.strip() for l in
             (ROOT / args.creds).read_text(encoding="utf-8").splitlines()
             if l.strip()]
    user, pwd = lines[0], lines[1]
    days = list(daterange(args.start, args.end))
    RAW.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    print(f"[*] {len(days)} days ({days[0]}..{days[-1]}), "
          f"instruments={args.instruments}")

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()

        page.goto(BASE, wait_until="networkidle", timeout=90000)
        page.click("a:has-text('Login/Signup')", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=60000)
        if page.locator("#username").count():
            page.fill("#username", user)
            page.fill("#password", pwd)
            page.click("#kc-login")
            page.wait_for_load_state("networkidle", timeout=90000)
        print("[+] login:", "OK" if "payload" in page.url.lower()
              or page.locator("text=Logout").count() else "?")

        tags = {"solexs": ["SLX"], "hel1os": ["HLD"],
                "both": ["SLX", "HLD"]}[args.instruments]
        summary = {}
        for tag in tags:
            print(f"[*] {tag}:")
            got, missing = harvest_tag(page, tag, days, RAW)
            summary[tag] = (got, missing)
            print(f"    -> {got}/{len(days)} present")

        browser.close()

    print("\n==== SUMMARY ====")
    for tag, (got, missing) in summary.items():
        print(f"{tag}: {got} downloaded/present; {len(missing)} absent on portal")
        for m in missing:
            print("   absent:", m)

    if args.forget:
        cred = ROOT / args.creds
        if cred.exists():
            cred.unlink()
            print("[+] credential file deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())