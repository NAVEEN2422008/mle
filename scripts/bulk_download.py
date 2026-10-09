#!/usr/bin/env python3
"""
Use Playwright to automate the "Select, Zip and DOWNLOAD" feature on PRADAN.
This creates a zip file that can be downloaded.
"""
import asyncio
from playwright.async_api import async_playwright

async def bulk_download():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Go to HEL1OS page
        await page.goto("https://pradan.issdc.gov.in/al1/protected/browse.xhtml?id=hel1os")
        await page.wait_for_load_state("networkidle")
        
        # Check if logged in
        content = await page.content()
        if "Sign in" in content or "login-pf" in content or "username" in content:
            print("Need to log in manually...")
            print("Please log in in the browser window...")
            for _ in range(60):
                await asyncio.sleep(5)
                content = await page.content()
                if "Sign in" not in content and "login-pf" not in content and "username" not in content:
                    print("Login detected!")
                    break
            else:
                print("Timeout waiting for login")
                return
        
        # Apply filter for May 2024
        print("Applying filter for May 2024...")
        await page.select_option('select[name*="filterTable"][name*="attr"]', "ObservationTime")
        await page.select_option('select[name*="filterTable"][name*="opr"]', "In")
        await page.fill('input[name*="datetime1"]', "2024-05-01 00:00:00")
        await page.fill('input[name*="datetime2"]', "2024-05-31 23:59:59")
        await page.click('button:has-text("Filter")')
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)
        
        # Click "Select, Zip and DOWNLOAD" button
        print("Clicking 'Select, Zip and DOWNLOAD'...")
        zip_button = await page.query_selector('button:has-text("Select, Zip and DOWNLOAD")')
        if zip_button:
            await zip_button.click()
            print("Clicked zip download button")
            
            # Wait for download
            async with page.expect_download() as download_info:
                await page.wait_for_timeout(5000)
            download = await download_info.value
            await download.save_as("hel1os_may2024.zip")
            print("Downloaded hel1os_may2024.zip")
        else:
            print("Could not find zip download button")
        
        # Now do SoLEXS
        print("\nProcessing SoLEXS...")
        await page.goto("https://pradan.issdc.gov.in/al1/protected/browse.xhtml?id=solexs")
        await page.wait_for_load_state("networkidle")
        
        print("Applying filter for SoLEXS May 2024...")
        await page.select_option('select[name*="filterTable"][name*="attr"]', "ObservationTime")
        await page.select_option('select[name*="filterTable"][name*="opr"]', "In")
        await page.fill('input[name*="datetime1"]', "2024-05-01 00:00:00")
        await page.fill('input[name*="datetime2"]', "2024-05-31 23:59:59")
        await page.click('button:has-text("Filter")')
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2000)
        
        print("Clicking 'Select, Zip and DOWNLOAD' for SoLEXS...")
        zip_button = await page.query_selector('button:has-text("Select, Zip and DOWNLOAD")')
        if zip_button:
            async with page.expect_download() as download_info:
                await zip_button.click()
            download = await download_info.value
            await download.save_as("solexs_may2024.zip")
            print("Downloaded solexs_may2024.zip")
        else:
            print("Could not find zip download button for SoLEXS")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        
        try:
            # Login first
            page = await browser.new_page()
            await page.goto("https://pradan.issdc.gov.in/al1/protected/browse.xhtml?id=hel1os")
            await page.wait_for_load_state("networkidle")
            
            # Check if logged in
            content = await page.content()
            if "Sign in" in content or "login-pf" in content or "username" in content:
                print("Need to log in manually...")
                print("Please log in in the browser window...")
                for _ in range(60):
                    await asyncio.sleep(5)
                    content = await page.content()
                    if "Sign in" not in content and "login-pf" not in content and "username" not in content:
                        print("Login detected!")
                        break
                else:
                    print("Timeout waiting for login")
                    return
            
            # Process HEL1OS May 2024
            print("\nProcessing HEL1OS May 2024...")
            await page.goto("https://pradan.issdc.gov.in/al1/protected/browse.xhtml?id=hel1os")
            await page.wait_for_load_state("networkidle")
            
            print("Applying filter for May 2024...")
            await page.select_option('select[name*="filterTable"][name*="attr"]', "ObservationTime")
            await page.select_option('select[name*="filterTable"][name*="opr"]', "In")
            await page.fill('input[name*="datetime1"]', "2024-05-01 00:00:00")
            await page.fill('input[name*="datetime2"]', "2024-05-31 23:59:59")
            await page.click('button:has-text("Filter")')
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)
            
            # Click "Select, Zip and DOWNLOAD"
            print("Clicking 'Select, Zip and DOWNLOAD'...")
            zip_button = await page.query_selector('button:has-text("Select, Zip and DOWNLOAD")')
            if zip_button:
                async with page.expect_download() as download_info:
                    await zip_button.click()
                download = await download_info.value
                await download.save_as("hel1os_may2024.zip")
                print("Downloaded hel1os_may2024.zip")
            else:
                print("Could not find zip download button")
            
            # Process SoLEXS
            print("\nProcessing SoLEXS May 2024...")
            await page.goto("https://pradan.issdc.gov.in/al1/protected/browse.xhtml?id=solexs")
            await page.wait_for_load_state("networkidle")
            
            print("Applying filter for SoLEXS May 2024...")
            await page.select_option('select[name*="filterTable"][name*="attr"]', "ObservationTime")
            await page.select_option('select[name*="filterTable"][name*="opr"]', "In")
            await page.fill('input[name*="datetime1"]', "2024-05-01 00:00:00")
            await page.fill('input[name*="datetime2"]', "2024-05-31 23:59:59")
            await page.click('button:has-text("Filter")')
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2000)
            
            print("Clicking 'Select, Zip and DOWNLOAD' for SoLEXS...")
            zip_button = await page.query_selector('button:has-text("Select, Zip and DOWNLOAD")')
            if zip_button:
                async with page.expect_download() as download_info:
                    await zip_button.click()
                download = await download_info.value
                await download.save_as("solexs_may2024.zip")
                print("Downloaded solexs_may2024.zip")
            else:
                print("Could not find zip download button for SoLEXS")
        
        finally:
            await browser.close()

asyncio.run(main())