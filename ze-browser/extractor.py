import asyncio
import random
import re

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

_MIN_TEXT_LEN = 200


async def extract(url: str, timeout_ms: int = 15000) -> dict:
    await asyncio.sleep(random.uniform(1.0, 3.0))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        try:
            ctx = await browser.new_context(
                user_agent=random.choice(_USER_AGENTS),
                viewport={"width": 1280, "height": 800},
            )
            page = await ctx.new_page()

            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
            except Exception:
                pass

            resp = None
            try:
                resp = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                except PlaywrightTimeoutError:
                    return {"url": url, "title": "", "text": "", "status_code": 504}

            title = await page.title()
            status_code = resp.status if resp else 200

            if status_code in (403, 429):
                return {"url": url, "title": title, "text": "", "status_code": 403}

            try:
                text = await page.inner_text("body")
            except Exception:
                text = ""

            if len(text) < _MIN_TEXT_LEN:
                content = await page.content()
                text = re.sub(r"<[^>]+>", " ", content)
                text = re.sub(r"\s+", " ", text).strip()

            if len(text) < _MIN_TEXT_LEN:
                return {"url": url, "title": title, "text": "", "status_code": 403}

            return {"url": url, "title": title, "text": text, "status_code": status_code}
        finally:
            await browser.close()
