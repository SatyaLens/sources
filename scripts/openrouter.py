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
import re
import yaml
from typing import Tuple

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except Exception:  # pragma: no cover - very unlikely
    raise

MD_PROCESSING_SKILL_URL = "https://raw.githubusercontent.com/semmet95/agent-skills/refs/heads/main/md-processing/SKILL.md"
SOURCE_QUESTION = "What are the top 10 latest most popular news outlets in the world listed in this document? Only output URLs of these news outlets separated by new lines. Do not output anything else."
FREE_MODELS_DOC = [
    "openai/gpt-oss-120b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "z-ai/glm-4.5-air:free"
]


def fetch_text(url: str) -> str:
    with urlopen(url, timeout=60) as r:
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

    status = -1
    try:
        with urlopen(req, timeout=60) as r:
            status = r.getcode()
            body = r.read().decode("utf-8")
    except Exception as e:
        print(f"Error making request to OpenRouter API: {e}", file=sys.stderr)
        body = ""

    return status, body

# TODO: add retry mechanism when hitting openrouter endpoints
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
        print(f"Openrouter response status: {status}", file=sys.stderr)
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

def get_latest_source() -> str:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    sources_dir = os.path.join(base_dir, "sources")

    try:
        entries = [os.path.join(sources_dir, fn) for fn in os.listdir(sources_dir)]
        files = [p for p in entries if os.path.isfile(p)]
    except Exception as e:
        print(f"Error listing sources directory {sources_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    if not files:
        print(f"No files found in {sources_dir}", file=sys.stderr)
        sys.exit(1)

    latest = max(files, key=lambda p: os.path.getmtime(p))

    try:
        with open(latest, 'r', encoding='utf-8') as f:
            latest_content = f.read()
    except Exception as e:
        print(f"Error reading latest file {latest}: {e}", file=sys.stderr)
        sys.exit(1)

    return latest_content

def remove_ingested_sources(source_docs: list[str]) -> list[str]:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    sources_dir = os.path.join(base_dir, "sources")

    # Load existing source files
    existing = []
    try:
        for fn in os.listdir(sources_dir):
            if not (fn.endswith('.yaml') or fn.endswith('.yml')):
                continue
            path = os.path.join(sources_dir, fn)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    doc = yaml.safe_load(f)
                if isinstance(doc, dict):
                    existing.append(doc)
            except Exception as e:
                print(f"Warning: failed to read/parse {path}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error listing sources directory {sources_dir}: {e}", file=sys.stderr)
        return source_docs

    cleaned: list[str] = []
    for doc_str in source_docs:
        try:
            doc = yaml.safe_load(doc_str)
        except Exception as e:
            print(f"Warning: failed to parse source_doc; not adding it to the source list it. Error: {e}", file=sys.stderr)
            continue
        if doc == None:
            print(f"Warning: skipping the following yaml string as it failed to load: {doc_str}", file=sys.stderr)
            continue
        duplicate = False
        for src in existing:
            if doc.get('name') == src.get('name') or doc.get('uri') == src.get('uri'):
                duplicate = True
                break
        if not duplicate:
            cleaned.append(doc_str)

    return cleaned

def get_source_docs(sample: str, sources: str, api_key: str) -> str:
    # TODO: generate yaml doc for once source at a time, however this consumes more requests and increases odds of failed requests
    content = (f"Extract schema from the following yaml document and store it as source_schema:\n\n"
        f"{sample}\n\n"
        f"Following is a list of urls of media outlets separated by new lines\n\n"
        f"{sources}\n\n"
        "Use web search to fetch information about these media outlets and create yaml docs for each of them following the source_schema schema. Do not output anything except for the yaml documents for these medial outlets separated by ---."
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

        source_docs = req_openrouter(payload, api_key)
        if source_docs != "":
            break
    if source_docs == "":
        print("Error: All models failed.", file=sys.stderr)
        sys.exit(1)
    return source_docs

def main():
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

    # load the most recently added source
    latest_source = get_latest_source()

    source_docs = get_source_docs(latest_source, source_list, api_key).split("---")
    source_docs = list(filter(str.strip, source_docs))

    # remove sources that are already in the `sources` directory
    unique_src_docs = remove_ingested_sources(source_docs)

    # Write each unique source YAML doc into the `sources/` folder.
    base_dir = os.path.dirname(os.path.dirname(__file__))
    sources_dir = os.path.join(base_dir, "sources")

    for doc_str in unique_src_docs:
        try:
            parsed = yaml.safe_load(doc_str)
        except Exception as e:
            print(f"Warning: failed to parse src_doc : {doc_str}: {e}", file=sys.stderr)
            continue

        filename = parsed.get('name')
        if filename == None or filename.strip() == '':
            print(f"Warning: invalid source name or failed to extract name field from : {doc_str}", file=sys.stderr)
            continue

        # sanitize name to use as filename
        filename = re.sub(r"[^A-Za-z0-9._-]+", "-", filename.strip())

        filename = filename + ".yaml"
        path = os.path.join(sources_dir, filename)

        # avoid overwriting existing files
        if os.path.exists(path):
            print(f"Warning: source file with name : {filename} already exists", file=sys.stderr)
            continue

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(doc_str.strip() + "\n")
        except Exception as e:
            print(f"Error writing {path}: {e}", file=sys.stderr)

if __name__ == "__main__":
    raise SystemExit(main())
