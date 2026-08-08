#!/usr/bin/env python3
"""
Web Fetch Layer — The Extraction Layer
====================================
Replicates Agnes AI's Web Fetch mechanism.
Acts as a headless scraper: fetches a URL, strips ads/nav/scripts,
converts HTML to clean Markdown the LLM can read word-for-word.
"""
import logging, time
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("web_fetch")

_DEFAULT_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
_STRIP_TAGS = ["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]


class WebFetch:
    def __init__(self, config: dict):
        fc = config.get("fetch", {})
        self.timeout = fc.get("timeout", 30)
        self.max_chars = fc.get("max_content_length", 50000)
        self.retries = fc.get("retry_attempts", 3)
        self.user_agent = fc.get("user_agent", _DEFAULT_UA)
        self.max_workers = fc.get("max_workers", 5)

    def fetch(self, url: str) -> Optional[Dict]:
        import requests
        from bs4 import BeautifulSoup
        import html2text

        h2m = html2text.HTML2Text()
        h2m.body_width = 0
        h2m.ignore_links = False
        h2m.ignore_images = True

        headers = {"User-Agent": self.user_agent}

        for attempt in range(1, self.retries + 1):
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout, allow_redirects=True)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for tag in soup.find_all(_STRIP_TAGS):
                    tag.decompose()

                title = soup.title.string.strip() if soup.title and soup.title.string else url
                main = soup.find("article") or soup.find("main") or soup.find("body") or soup
                markdown = h2m.handle(str(main)).strip()

                if len(markdown) > self.max_chars:
                    markdown = markdown[:self.max_chars] + "\n\n...[truncated]..."

                logger.info(f"Web Fetch OK: {url} ({len(markdown)} chars)")
                return {"url": url, "title": title, "markdown": markdown, "char_count": len(markdown)}
            except Exception as e:
                if attempt < self.retries:
                    logger.warning(f"Fetch attempt {attempt}/{self.retries} failed for {url}: {e}")
                    time.sleep(2 * attempt)
                else:
                    logger.error(f"Fetch failed for {url}: {e}")
                    return None

    def fetch_batch(self, urls: List[str]) -> List[Dict]:
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self.fetch, url): url for url in urls}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Batch fetch error for {url}: {e}")
        url_order = {url: i for i, url in enumerate(urls)}
        results.sort(key=lambda x: url_order.get(x["url"], 999))
        return results
