import os
import json
import asyncio
from playwright.async_api import async_playwright

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(THIS_DIR, "auth.json")

async def dump_tweet_containers(username: str):
    if not os.path.exists(COOKIES_FILE):
        raise RuntimeError(f"Cookie file not found: {COOKIES_FILE}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headless=False = show browser
        context = await browser.new_context(storage_state=COOKIES_FILE)
        page = await context.new_page()

        url = f"https://x.com/search?q=from%3A{username}&f=live"
        print(f"🔗 Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded")

        # Wait manually so you can inspect what’s happening
        print("⏳ Waiting 15 seconds for tweets to load…")
        await page.wait_for_timeout(15000)

        containers = await page.query_selector_all("article[data-testid='tweet']")
        if not containers:
            print("❌ No tweet containers found.")
        else:
            print(f"✅ Found {len(containers)} tweet containers.")

        # Keep browser open so you can see the final page
        print("🔍 Inspect the page. Close manually when done.")
        await page.pause()

        await browser.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python dump_tweets_html.py <username>")
    else:
        username = sys.argv[1]
        asyncio.run(dump_tweet_containers(username))
