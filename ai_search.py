#!/usr/bin/env python3
"""
AI Search Layer — The Inquiry Layer
==================================
Replicates Agnes AI's AI Search mechanism.
Sends programmatic search requests, gathers structured snippets
(titles, descriptions, ranked links), and supports iterative
sub-queries for Deep / Wide research modes.
"""
import logging
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, urlparse, parse_qs

logger = logging.getLogger("ai_search")


class AISearch:
    def __init__(self, config: dict):
        self.config = config
        self.default_max = config.get("search", {}).get("max_results", 10)

    def search(self, query: str, max_results: Optional[int] = None) -> List[Dict]:
        max_results = max_results or self.default_max

        # Try ddgs library first
        try:
            from ddgs import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", r.get("link", "")),
                        "snippet": r.get("body", r.get("snippet", "")),
                    })
            logger.info(f"AI Search (ddgs): {len(results)} results for '{query}'")
            return results
        except ImportError:
            logger.debug("ddgs not installed — using fallback")
        except Exception as e:
            logger.warning(f"ddgs search failed: {e} — trying fallback")

        return self._search_ddg_html(query, max_results)

    def _search_ddg_html(self, query: str, max_results: int) -> List[Dict]:
        import requests
        from bs4 import BeautifulSoup

        url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for item in soup.select(".result"):
                title_el = item.select_one(".result__title")
                link_el = item.select_one(".result__url")
                snippet_el = item.select_one(".result__snippet")
                if not title_el:
                    continue
                href = link_el.get("href", "") if link_el else ""
                if "uddg=" in href:
                    qs = parse_qs(urlparse(href).query)
                    href = qs.get("uddg", [href])[0]
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url": href,
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                })
                if len(results) >= max_results:
                    break
            logger.info(f"AI Search (html): {len(results)} results for '{query}'")
            return results
        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return []

    def deep_search(self, topic: dict) -> List[Dict]:
        query = topic["query"]
        sub_queries = topic.get("sub_queries", [])
        depth = topic.get("search_depth", "deep")
        max_results = topic.get("max_results", self.default_max)

        all_queries = [query]
        if depth == "deep" and sub_queries:
            all_queries.extend(sub_queries)
        elif depth == "wide":
            all_queries.extend(sub_queries)
            all_queries.extend([
                query + " latest news",
                query + " 2026",
                query + " analysis report",
                query + " developments",
            ])

        logger.info(f"Deep search: {len(all_queries)} queries for '{topic.get('name', query)}'")

        all_results: List[Dict] = []
        seen_urls: set = set()

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(self.search, q, max_results): q for q in all_queries}
            for future in as_completed(futures):
                q_text = futures[future]
                try:
                    for r in future.result():
                        url = r.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            r["source_query"] = q_text
                            all_results.append(r)
                except Exception as e:
                    logger.error(f"Query '{q_text}' failed: {e}")

        all_results.sort(key=lambda x: x.get("source_query", "") != query)
        logger.info(f"Deep search complete: {len(all_results)} unique results")
        return all_results
