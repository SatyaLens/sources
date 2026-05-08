#!/usr/bin/env python3
"""OpenRouter helper: try multiple models until one returns HTTP 200 and print assistant reply.

Usage:
  python3 scripts/openrouter.py path/to/page.md

Environment:
  OPENROUTER_API_KEY must be set.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Tuple

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except Exception:  # pragma: no cover - very unlikely
    raise

MD_PROCESSING_SKILL_URL = "https://raw.githubusercontent.com/semmet95/agent-skills/refs/heads/main/md-processing/SKILL.md"
SOURCE_QUESTION = "What are the top 10 latest most popular news outlets in the world listed in this document? Only output URLs of these news outlets separated by new lines. Do not output anything else."
FREE_MODELS_DOC = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "google/gemma-4-26b-a4b-it:free",
]


def fetch_text(url: str) -> str:
    with urlopen(url) as r:
        return r.read().decode("utf-8")

def fetch_content(path: str) -> str:
    with open(path, 'r') as f:
        return f.read()

def post_openrouter(api_key: str, payload: dict) -> Tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urlopen(req) as r:
            status = r.getcode()
            body = r.read().decode("utf-8")
    except HTTPError as e:
        status = e.code
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = ""

    return status, body

def req_openrouter(payload: dict, api_key: str) -> str:
    status, body = post_openrouter(api_key, payload)

    if status == 200:
        try:
            data = json.loads(body)
        except Exception as e:
            print(f"Failed to parse JSON response: {e}", file=sys.stderr)
            print(body)
            sys.exit(1)

        # Extract assistant reply
        reply = None
        try:
            reply = data["choices"][0]["message"]["content"]
            return reply
        except Exception as e:
            print(f"Failed to access key [choices][0][message][content]: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        return ""

def process_raw_doc(md_processing_skill: str, md_doc: str, api_key: str) -> str:
    for model in FREE_MODELS_DOC:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": md_processing_skill},
                {
                    "role": "user",
                    "content": "Here is a web page in Markdown:\n\n" + md_doc + "\n\nAnswer this question:\n" + SOURCE_QUESTION
                },
            ],
        }

        raw_source_list = req_openrouter(payload, api_key)
        if raw_source_list != "":
            break
    if raw_source_list == "":
        print("Error: All models failed.", file=sys.stderr)
        sys.exit(1)
    return raw_source_list

def process_raw_srcs(raw_source_list: str, api_key: str) -> str:
    content = (f"Here is a raw list of URLs of news outlets with each line containing one or more unformatted URLs:\n\n"
        f"{raw_source_list}\n\n"
        f"Use web search to access these URLs and discard those that are invalid. Do not scrape the web page, only check if the URL is valid\n"
        "Based on successful web searches, return a list of corresponding properly formatted URLs witout any extra test. Keep only one URL per line."
    )
    for model in FREE_MODELS_DOC:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": content
                },
            ],
            "tools": [
                {"type": "openrouter:web_search"}
            ]
        }

        source_list = req_openrouter(payload, api_key)
        if source_list != "":
            break
    if source_list == "":
        print("Error: All models failed.", file=sys.stderr)
        sys.exit(1)
    return source_list

def main() -> str:
    if len(sys.argv) < 2:
        print("Usage: openrouter.py TMP_MD", file=sys.stderr)
        sys.exit(1)

    tmp_md = sys.argv[1]

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # Fetch md processing skill
    try:
        md_processing_skill = fetch_text(MD_PROCESSING_SKILL_URL)
    except Exception as e:
        print(f"Error: failed to fetch skill from {MD_PROCESSING_SKILL_URL}: {e}", file=sys.stderr)
        sys.exit(1)

    # Fetch md file content
    try:
        md_doc = fetch_content(tmp_md)
    except Exception as e:
        print(f"Error: failed to fetch content from file {tmp_md}: {e}", file=sys.stderr)
        sys.exit(1)

    raw_source_list = process_raw_doc(md_processing_skill, md_doc, api_key)

    # openrouter call to get a clean formatted list of source urls
    source_list = process_raw_srcs(raw_source_list, api_key)

    # openrouter call for each source
    # input: SourceInput schema from oap.yaml + latest added source from sources folder
    # output: properly formatted source doument
    # print the document

    return source_list


if __name__ == "__main__":
    raise SystemExit(main())
