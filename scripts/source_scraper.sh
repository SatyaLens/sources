#!/bin/bash
set -euo pipefail

URL="$TOP_SOURCES_LIST"

if [[ -z "$URL" ]]; then
  echo "TOP_SOURCES_LIST env var not set" >&2
  exit 1
fi

if [[ -z "${FIRECRAWL_API_KEY:-}" ]]; then
  echo "Error: FIRECRAWL_API_KEY is not set." >&2
  exit 1
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "Error: OPENROUTER_API_KEY is not set." >&2
  exit 1
fi

# Temp file for the page markdown
TMP_MD="$(mktemp)"
echo "Saving scraped page to $TMP_MD"
# trap 'rm -f "$TMP_MD"' EXIT

# Scrape page via Firecrawl Python helper
python3 scripts/scrape_firecrawl.py "$URL" >"$TMP_MD"

md_processing_skill=$(curl https://raw.githubusercontent.com/semmet95/agent-skills/refs/heads/main/md-processing/SKILL.md)

# Build JSON payload for OpenRouter using jq
# Read the markdown as a raw file to avoid quoting issues.
REQ_JSON="$(
  jq -n \
    --rawfile page "$TMP_MD" \
    --arg question "What are the top 10 latest most popular news outlets listed in this document?" \
    --arg md_processing_skill "$md_processing_skill" \
    '{
    model: "openrouter/free",
    messages: [
      {
        "role": "system",
        "content": "$md_processing_skill"
      },
      {
        role: "user",
        content:
          "You are a markdown processing expert and AI research assistant. Here is a web page in Markdown:\n\n" +
          $page +
          "\n\nAnswer this question in 2-3 concise sentences:\n" +
          $question
      }
    ]
  }'
)"

# Call OpenRouter chat completions API
RESPONSE="$(curl -sS https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d "$REQ_JSON")"

# 4) Print just the assistant's reply
echo "$RESPONSE" | jq -r '.choices[0].message.content'
