# scraper/fetch.py

import os
import json
import asyncio
from datetime import datetime
from typing import List, Dict
from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

THIS_DIR     = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(THIS_DIR, "auth.json")
X_SEARCH_URL = "https://x.com/search?q=from%3A{}&f=live"
MAX_TWEETS_PER_FETCH = 20

async def scrape_tweets(username: str, max_tweets: int = MAX_TWEETS_PER_FETCH) -> List[Dict]:
    """
    Uses saved cookies (auth.json) from the same folder as this file to load
    the user’s 'live' timeline in reverse-chronological order. Returns a list
    of {"content": str, "timestamp": datetime} up to max_tweets.
    """

    # 1) Ensure auth.json exists
    if not os.path.exists(COOKIES_FILE):
        raise RuntimeError(f"Cookie file '{COOKIES_FILE}' not found. Create it via save_cookies.py.")

    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # If data is a raw list of cookies, wrap into Playwright storage_state format
    if isinstance(data, list):
        data = {"cookies": data, "origins": []}
        with open(COOKIES_FILE, "w", encoding="utf-8") as fw:
            json.dump(data, fw, indent=2)
    elif not isinstance(data, dict) or "cookies" not in data:
        raise RuntimeError(f"Invalid format in '{COOKIES_FILE}'. Expected a top-level 'cookies' key.")

    # 2) Build the chronological “live” search URL
    url = X_SEARCH_URL.format(username)
    tweets, seen_texts = [], set()

    # 3) Launch Playwright, load storage_state from auth.json
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=COOKIES_FILE)
        page = await context.new_page()

        # 4) Navigate to the “live” search URL, retry once if needed
        try:
            await page.goto(url, timeout=60000, wait_until="networkidle")
        except PWTimeoutError:
            await asyncio.sleep(2)
            await page.goto(url, timeout=60000, wait_until="networkidle")

        # Wait for tweets to render
        await page.wait_for_timeout(5000)

        # 5) Check for redirect to login/challenge
        final_url = page.url
        if "login" in final_url or "challenge" in final_url:
            html_dump = await page.content()
            dump_html = os.path.join(THIS_DIR, f"{username}_redirect.html")
            with open(dump_html, "w", encoding="utf-8") as f:
                f.write(html_dump)
            screenshot_path = os.path.join(THIS_DIR, f"{username}_redirect.png")
            await page.screenshot(path=screenshot_path, full_page=True)
            await browser.close()
            raise RuntimeError(
                f"⚠️ Redirected to login/challenge page ({final_url}). "
                f"Cookie expired or invalid. HTML: {dump_html}, screenshot: {screenshot_path}"
            )

        # 6) Wait for tweet container, with extended timeout and debug on failure
        try:
            await page.wait_for_selector("article[data-testid='tweet']", timeout=30000)
        except PWTimeoutError:
            # Dump HTML and screenshot for debugging
            html_dump = await page.content()
            dump_html = os.path.join(THIS_DIR, f"{username}_no_tweets.html")
            with open(dump_html, "w", encoding="utf-8") as f:
                f.write(html_dump)

            screenshot_path = os.path.join(THIS_DIR, f"{username}_no_tweets.png")
            await page.screenshot(path=screenshot_path, full_page=True)

            await browser.close()
            raise RuntimeError(
                f"⚠️ No tweets found for @{username} within 30s. "
                f"HTML: {dump_html}, screenshot: {screenshot_path}"
            )

        # 7) Scroll & collect tweets
        last_height = await page.evaluate("() => document.body.scrollHeight")

        while len(tweets) < max_tweets:
            tweet_blocks = await page.query_selector_all("article[data-testid='tweet']")
            for block in tweet_blocks:
                try:
                    text_el = await block.query_selector("[data-testid='tweetText']")
                    if not text_el:
                        text_el = await block.query_selector("div[lang]")
                    time_el = await block.query_selector("time")
                    if text_el and time_el:
                        content = (await text_el.inner_text()).strip()
                        ts_str = await time_el.get_attribute("datetime")
                        timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if content not in seen_texts:
                            seen_texts.add(content)
                            tweets.append({"content": content, "timestamp": timestamp})
                    if len(tweets) >= max_tweets:
                        break
                except Exception:
                    continue

            if len(tweets) >= max_tweets:
                break

            await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            new_height = await page.evaluate("() => document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        await browser.close()

    return tweets

# Example standalone test:
# async def main():
#     result = await scrape_tweets("QuakesToday", 5)
#     print(result)
# asyncio.run(main())
