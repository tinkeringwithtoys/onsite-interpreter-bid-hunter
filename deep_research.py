#!/usr/bin/env python3
"""
Deep Research Engine — Twice-Daily Automated Research
=====================================================
Replicates Agnes AI's AI Search + Web Fetch pattern:
  1. AI Search  -> DuckDuckGo queries, snippet gathering, ranked links
  2. Web Fetch  -> HTML-to-Markdown extraction from top URLs
  3. Synthesis  -> Agnes AI LLM generates a structured research report

Runs on GitHub Actions twice a day. No server needed.
"""
import os, sys, json, logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ai_search import AISearch
from web_fetch import WebFetch
from synthesizer import Synthesizer
from notify import Notifier

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("deep_research")


class DeepResearch:
    def __init__(self, config_path="research_config.yaml"):
        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.search = AISearch(self.config)
        self.fetcher = WebFetch(self.config)
        self.synthesizer = Synthesizer(self.config)
        self.notifier = Notifier(self.config)
        self.output_dir = Path(self.config.get("output", {}).get("dir", "reports"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_topic(self, topic: dict) -> dict:
        name = topic.get("name", "Untitled")
        query = topic["query"]
        depth = topic.get("search_depth", "deep")
        max_results = topic.get("max_results", 10)
        fetch_depth = topic.get("fetch_depth", 5)

        logger.info(f"=== Topic: {name} ===")
        logger.info(f"Main query: {query} | depth={depth} | fetch={fetch_depth}")

        # Step 1: AI Search
        logger.info("[1/3] AI Search — gathering snippets and ranked links...")
        if depth in ("deep", "wide"):
            search_results = self.search.deep_search(topic)
        else:
            search_results = self.search.search(query, max_results=max_results)
        logger.info(f"  -> {len(search_results)} unique results")
        if not search_results:
            logger.warning("No search results — skipping topic.")
            return {"name": name, "query": query, "report": "No results found.",
                    "sources": [], "search_count": 0, "fetch_count": 0}

        # Step 2: Web Fetch
        logger.info(f"[2/3] Web Fetch — extracting top {fetch_depth} URLs...")
        urls_to_fetch = [r["url"] for r in search_results[:fetch_depth] if r.get("url")]
        fetched = self.fetcher.fetch_batch(urls_to_fetch)
        logger.info(f"  -> {len(fetched)} pages fetched")

        # Step 3: Synthesis
        logger.info("[3/3] Synthesis — Agnes AI generating research report...")
        report = self.synthesizer.synthesize(
            topic_name=name, query=query,
            search_results=search_results, fetched_content=fetched)
        logger.info(f"  -> Report: {len(report)} chars")

        return {"name": name, "query": query, "report": report,
                "sources": [{"title": r.get("title",""), "url": r.get("url","")} for r in search_results],
                "search_count": len(search_results), "fetch_count": len(fetched)}

    def run(self):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M-UTC")
        topics = self.config.get("topics", [])
        logger.info(f"Deep Research started — {len(topics)} topic(s) — {ts}")

        all_results = []
        for topic in topics:
            try:
                all_results.append(self.run_topic(topic))
            except Exception as e:
                logger.error(f"Topic '{topic.get('name','?')}' failed: {e}", exc_info=True)
                all_results.append({"name": topic.get("name","Unknown"),
                    "query": topic.get("query",""), "report": f"Error: {e}",
                    "sources": [], "search_count": 0, "fetch_count": 0})

        # Save individual reports
        for r in all_results:
            safe = r["name"].replace(" ","_").replace("/","-").lower()
            filepath = self.output_dir / f"{ts}__{safe}.md"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# Deep Research: {r['name']}\n\n")
                f.write(f"**Date:** {ts}\n\n")
                f.write(f"**Query:** {r.get('query','')}\n\n")
                f.write(f"**Sources found:** {r.get('search_count',0)} | **Pages fetched:** {r.get('fetch_count',0)}\n\n")
                f.write("---\n\n")
                f.write(r["report"])
                f.write("\n\n---\n\n## Sources\n\n")
                for s in r.get("sources", []):
                    f.write(f"- [{s['title']}]({s['url']})\n")
            logger.info(f"Saved: {filepath}")

        # Save combined JSON
        json_path = self.output_dir / f"{ts}__summary.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": ts, "topics": all_results}, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved summary: {json_path}")

        # Notify
        self.notifier.notify(all_results, ts)
        logger.info("Deep Research run complete!")
        return all_results


def main():
    config_path = os.environ.get("RESEARCH_CONFIG", "research_config.yaml")
    if not Path(config_path).exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    DeepResearch(config_path).run()


if __name__ == "__main__":
    main()
