# Deep Research Engine

Automated **deep research** that runs **twice a day** on GitHub Actions — no server needed.

Replicates the **AI Search + Web Fetch** pattern used by [Agnes AI](https://agnes-ai.com/):

| Layer | What it does | Tool |
|-------|-------------|------|
| AI Search | Sends programmatic search queries, gathers snippets & ranked links | DuckDuckGo (`ddgs`) |
| Web Fetch | Extracts full page content from top URLs, converts HTML to Markdown | `requests` + `html2text` |
| Synthesis | LLM reads everything and writes a structured research report | Agnes AI API (free, OpenAI-compatible) |

## How It Works

```
research_config.yaml     +-->  AI Search    (DuckDuckGo queries -> ranked links + snippets)
  topics (queries)              |
                                v
                          Web Fetch    (HTML -> Markdown -> full page content)
                                |
  AGNES_API_KEY                   v
  model settings     +-->  Synthesizer  (Agnes AI LLM -> research report)
                                |
                                v
                          reports/      (Markdown files + summary JSON, committed by CI)
```

## Setup

### 1. Get a free Agnes AI API key
Sign up at [platform.agnes-ai.com](https://platform.agnes-ai.com) and create an API key.

### 2. Add the key as a GitHub secret
Go to your repo -> **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**:
- Name: `AGNES_API_KEY`
- Value: your API key

### 3. (Optional) Set up notifications
Add secrets for Discord or Telegram (see `.env.example`).

### 4. Configure your research topics
Edit `research_config.yaml`:
```yaml
topics:
  - name: "My Research Topic"
    query: "main search query"
    sub_queries: ["sub-query 1", "sub-query 2"]
    max_results: 10
    fetch_depth: 5
    search_depth: deep  # shallow | deep | wide
```

### 5. Run it
The workflow runs automatically at **06:00 and 18:00 UTC**. To trigger manually:
- Go to **Actions** tab -> **Deep Research** -> **Run workflow**

## Search Modes

| Mode | Behavior |
|------|----------|
| `shallow` | Single query, snippets only |
| `deep` | Main query + sub-queries, merged & deduped |
| `wide` | Main + sub + auto-generated variations for broad coverage |

## Output

Reports are saved to `reports/` as Markdown files and committed automatically:
```
reports/
  2026-08-08_0600-UTC__ai_industry_trends.md
  2026-08-08_0600-UTC__tech_news_digest.md
  2026-08-08_0600-UTC__summary.json
```

## Tech Stack
- **Search**: DuckDuckGo (`ddgs` library) — free, no API key
- **Fetch**: `requests` + `BeautifulSoup` + `html2text`
- **LLM**: Agnes AI API (`openai` SDK, OpenAI-compatible, free)
- **CI/CD**: GitHub Actions (cron schedule, no server)
- **Notifications**: Discord / Telegram (optional)
