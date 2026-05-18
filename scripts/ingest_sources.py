#!/usr/bin/env python3
"""Source doc specific logic for ingest_sources.py"""

import os
import re
import sys
import yaml

import helper
import openrouter

MD_PROCESSING_SKILL_URL = os.getenv(
    "MD_PROCESSING_SKILL_URL",
    "https://raw.githubusercontent.com/semmet95/agent-skills/refs/heads/main/md-processing/SKILL.md"
)
SOURCE_FILTER_PROMPT = os.getenv(
    "SOURCE_FILTER_PROMPT",
    "What are the top 10 latest most popular news outlets in the world listed in this document? Only output URLs of these news outlets separated by new lines. Do not output anything else."
)
SOURCE_CLEANUP_PROMPT = os.getenv(
    "SOURCE_CLEANUP_PROMPT",
    (
        "Use web search to access these URLs and discard those that are invalid. Do not scrape the web page, only check if the URL is valid"
        "Based on successful web searches, return a list of corresponding properly formatted URLs witout any extra test. Keep only one URL per line."
    )
)
SOURCE_DOC_GEN_PROMPT = os.getenv(
    "SOURCE_DOC_GEN_PROMPT",
    "Use web search to fetch information about these media outlets and create yaml docs for each of them following the source_schema schema. Do not output anything except for the yaml documents for these medial outlets separated by ---"
)

def remove_ingested_sources(source_docs: list[str], sources_dir: str) -> list[str]:
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

def write_source_docs(source_docs: list[str], sources_dir: str):
    for doc_str in source_docs:
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

def main():
    if len(sys.argv) < 2:
        print("Usage: openrouter.py TMP_MD", file=sys.stderr)
        sys.exit(1)

    tmp_md = sys.argv[1]

    # Fetch md processing skill
    try:
        md_processing_skill = helper.get_text_from_url(MD_PROCESSING_SKILL_URL)
    except Exception as e:
        print(f"Error: failed to fetch skill from {MD_PROCESSING_SKILL_URL}: {e}", file=sys.stderr)
        sys.exit(1)

    # Fetch md file content
    try:
        md_doc = helper.get_text_from_file(tmp_md)
    except Exception as e:
        print(f"Error: failed to fetch content from file {tmp_md}: {e}", file=sys.stderr)
        sys.exit(1)

    req_content = "Here is a web page in Markdown:\n\n" + md_doc + "\n\nAnswer this question:\n" + SOURCE_FILTER_PROMPT
    raw_source_list =  openrouter.req_w_addons(req_content, skill=md_processing_skill)
    if raw_source_list == "":
        print("Error: failed to get raw source list from openrouter", file=sys.stderr)
        sys.exit(1)

    # openrouter call to get a clean formatted list of source urls
    req_content = (
        "Here is a raw list of URLs of news outlets with each line containing one or more unformatted URLs:"
        f"\n\n{raw_source_list}\n\n"
        f"{SOURCE_CLEANUP_PROMPT}"
    )
    source_list = openrouter.req_w_addons(req_content, tools=[openrouter.WEB_SEARCH_TOOL])
    if source_list == "":
        print("Error: failed to get filtered list of source urls", file=sys.stderr)
        sys.exit(1)

    # load the source input example
    src_input_schema = helper.get_oapi_spec()['components']['schemas']['SourceInput']
    src_example = src_input_schema.get('example')
    
    # generate source docs from the source url list
    req_content = (
        "Extract schema from the following yaml document and store it as source_schema:"
        f"\n\n{src_example}\n\n"
        "Following is a list of urls of media outlets separated by new lines:"
        f"\n\n{source_list}\n\n"
        f"{SOURCE_DOC_GEN_PROMPT}"
    )
    src_docs_str = openrouter.req_w_addons(req_content, tools=[openrouter.WEB_SEARCH_TOOL])
    if src_docs_str == "":
        print("Error: failed to generate source docs from source urls", file=sys.stderr)
        sys.exit(1)

    source_docs = src_docs_str.split("---")
    source_docs = list(filter(str.strip, source_docs))
    
    sources_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources")

    # remove sources that are already in the `sources` directory
    unique_src_docs = remove_ingested_sources(source_docs, sources_dir)

    # Write each unique source YAML doc into the `sources/` folder
    write_source_docs(unique_src_docs, sources_dir)    

if __name__ == "__main__":
    raise SystemExit(main())
