#!/usr/bin/env python3
"""
Synthesizer — LLM Research Report Generation
==========================================
Uses the Agnes AI API (OpenAI-compatible, free) to synthesise
search snippets and fetched page content into a structured
deep-research report.
"""
import os, logging
from typing import Dict, List

logger = logging.getLogger("synthesizer")

_SYSTEM_PROMPT = """\
You are a deep-research AI analyst. You receive web search snippets and
fetched page content, then produce a comprehensive, well-structured
Markdown research report.

Format your report as:
## Executive Summary
(2-3 paragraphs)

## Key Findings
- Bullet points of the most important discoveries

## Detailed Analysis
(Sectioned analysis with sub-headings as needed)

## Notable Trends & Patterns
(What's changing, emerging, or declining)

## Sources Reviewed
(Inline references to the URLs provided)

Guidelines:
- Cite sources inline as [1], [2], etc., matching the numbered list.
- Be factual — do not fabricate information not present in the data.
- If information is conflicting, note the conflict.
- Keep it concise but thorough (800-2000 words).
"""


class Synthesizer:
    def __init__(self, config: dict):
        mc = config.get("model", {})
        self.base_url = mc.get("base_url", "https://apihub.agnes-ai.com/v1")
        self.model = mc.get("name", "Agnes-2.5-Flash")
        self.max_tokens = mc.get("max_tokens", 4096)
        self.temperature = mc.get("temperature", 0.7)
        self.api_key = os.environ.get("AGNES_API_KEY", "")
        if not self.api_key:
            logger.warning("AGNES_API_KEY not set — synthesis will be skipped!")

    def _build_user_prompt(self, topic_name, query, search_results, fetched_content):
        lines = ["# Research Topic: " + topic_name, "# Primary Query: " + query, "",
                 "## Search Snippets (AI Search Results)", ""]
        for i, r in enumerate(search_results, 1):
            lines.append("[" + str(i) + "] " + r.get('title', 'No title'))
            lines.append("    URL: " + r.get('url', ''))
            lines.append("    Snippet: " + r.get('snippet', '')[:300])
            lines.append("")

        if fetched_content:
            lines += ["## Fetched Page Content (Web Fetch Results)", ""]
            for i, page in enumerate(fetched_content, 1):
                lines.append("### Page " + str(i) + ": " + page.get('title', page['url']))
                lines.append("URL: " + page['url'])
                lines.append("Source ref: [" + str(i) + "]")
                lines.append("")
                lines.append(page.get("markdown", "")[:8000])
                lines.append("")
        else:
            lines += ["## Fetched Page Content", "(No pages fetched — rely on snippets only.)", ""]
        return "\n".join(lines)

    def synthesize(self, topic_name, query, search_results, fetched_content) -> str:
        if not self.api_key:
            return ("## Error\n\nAGNES_API_KEY not set — cannot generate report.\n\n"
                    "Set the AGNES_API_KEY secret in your GitHub repository:\n"
                    "Settings -> Secrets and variables -> Actions -> New repository secret")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            user_prompt = self._build_user_prompt(topic_name, query, search_results, fetched_content)

            logger.info("Calling Agnes AI (" + self.model + ") for synthesis...")
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            report = response.choices[0].message.content.strip()
            logger.info("Synthesis complete: " + str(len(report)) + " chars")
            return report
        except Exception as e:
            logger.error("Synthesis failed: " + str(e), exc_info=True)
            return "## Synthesis Error\n\nThe LLM synthesis failed: " + str(e) + "\n\nRaw search results and fetched content were still saved."
