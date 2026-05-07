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
trap 'rm -f "$TMP_MD"' EXIT

# Scrape page via Firecrawl Python helper
python3 scripts/scrape_firecrawl.py "$URL" >"$TMP_MD"

# Process the scraped document using LLMs
python3 scripts/openrouter.py "$TMP_MD"
