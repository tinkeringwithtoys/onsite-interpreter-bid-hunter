#!/usr/bin/env python3
"""
Notifier — Send Deep Research Results
====================================
Supports Discord webhooks and Telegram bots.
Configure via research_config.yaml -> notify section.
"""
import os, logging
import requests

logger = logging.getLogger("notify")


class Notifier:
    def __init__(self, config: dict):
        nc = config.get("notify", {})
        self.discord_webhook = os.environ.get(
            "DISCORD_WEBHOOK_URL", nc.get("discord", {}).get("webhook_url", ""))
        self.telegram_token = os.environ.get(
            "TELEGRAM_BOT_TOKEN", nc.get("telegram", {}).get("bot_token", ""))
        self.telegram_chat_id = os.environ.get(
            "TELEGRAM_CHAT_ID", nc.get("telegram", {}).get("chat_id", ""))

    def notify(self, results: list, timestamp: str):
        summary = self._build_summary(results, timestamp)
        if self.discord_webhook:
            self._send_discord(summary)
        if self.telegram_token and self.telegram_chat_id:
            self._send_telegram(summary)

    def _build_summary(self, results: list, ts: str) -> str:
        lines = ["**Deep Research Report — " + ts + "**", ""]
        for r in results:
            lines.append("**" + r['name'] + "**")
            lines.append("  Sources: " + str(r.get('search_count', 0)) + " | Pages fetched: " + str(r.get('fetch_count', 0)))
            preview = r.get("report", "")[:500]
            lines.append("  Preview: " + preview + "...")
            lines.append("")
        return "\n".join(lines)

    def _send_discord(self, message: str):
        try:
            for i in range(0, len(message), 1900):
                requests.post(self.discord_webhook, json={"content": message[i:i+1900]}, timeout=10)
            logger.info("Discord notification sent")
        except Exception as e:
            logger.error("Discord notify failed: " + str(e))

    def _send_telegram(self, message: str):
        try:
            url = "https://api.telegram.org/bot" + self.telegram_token + "/sendMessage"
            for i in range(0, len(message), 4000):
                requests.post(url, json={
                    "chat_id": self.telegram_chat_id,
                    "text": message[i:i+4000],
                    "parse_mode": "Markdown",
                }, timeout=10)
            logger.info("Telegram notification sent")
        except Exception as e:
            logger.error("Telegram notify failed: " + str(e))
