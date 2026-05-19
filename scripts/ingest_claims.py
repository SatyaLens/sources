#!/usr/bin/env python3

import glob
import json
import os
import sys
import yaml

import helper
import newsdata_io
import openrouter

API_BASE_URL = os.environ["API_BASE_URL"]
API_KEY = os.environ["API_KEY"]

FALSIFIABLE_CLAIM_SKILL_URL = os.getenv(
    "FALSIFIABLE_CLAIM_SKILL_URL",
    "https://raw.githubusercontent.com/semmet95/agent-skills/refs/heads/main/determine-falsifialbe-claim/SKILL.md"
)
CLAIM_FILTER_PROMPT = os.getenv(
    "CLAIM_FILTER_PROMPT",
    (
        "Use web search tool to visit the link for each article, access the content and then assess if it is a falsifiable claim."
        "Out of these 10 articles, only return 1 article that best fits the falsifiable claim criterion."
        "Prefer claims that have been made by the news source directly"
        "Keep the json structure of the claims the same as the original schema in the input. Do not add remove, or modify any key or value in the json string."
        "Only output the plain json array string that I can safely unmarshal."
        "Do not format the string. Do not output anything else."
    )
)

def update_claim_fields(srcDigest: str, claim):
    claim["sourceUriDigest"] = srcDigest
    claim["summary"] = claim["description"]
    claim["uri"] = claim["link"]

def get_claim_docs(claims_dir: str):
    # Find all YAML files in claims directory and subdirectories
    yaml_files = glob.glob(os.path.join(claims_dir, "**", "*.yaml"), recursive=True)
    yaml_files.extend(glob.glob(os.path.join(claims_dir, "**", "*.yml"), recursive=True))
    
    claims_array = []
    for yaml_file in yaml_files:
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                claim_data = yaml.safe_load(f)
                if claim_data:  # Only add if file is not empty
                    claims_array.append(claim_data)
        except Exception as e:
            print(f"Error loading YAML file {yaml_file}: {e}", file=sys.stderr)
    
    return claims_array

def get_new_claims(all_claim_docs, new_claims, srcUriDigest):
    unique_claims = []

    for claim in new_claims:
        update_claim_fields(srcUriDigest, claim)
        new_claim = True
        for claim_doc in all_claim_docs:
            if claim["uri"] == claim_doc["uri"] or claim["title"] == claim_doc["title"]:
                new_claim = False
                break
        if new_claim:
            unique_claims.append(claim)

    return unique_claims

def create_claim_docs(claims: list, srcName: str):
    claim_input_schema = helper.get_oapi_spec()['components']['schemas']['ClaimInput']
    claim_example = claim_input_schema.get('example')

    # Custom representer to force double quotes around strings
    def quoted_str_representer(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')
    
    yaml.add_representer(str, quoted_str_representer)

    for claim in claims:
        claim_doc = {}
        # keep only relevant fields in the claims
        for key in claim_example.keys():
            claim_doc[key] = str(claim[key])
        
        filename = claim_doc["title"].lower()
        if len(filename) > 30:
            filename = filename[:30]
        filename = helper.clean_filepath(filename)
        filename = f"{filename}.yaml"

        dirname = srcName.lower()
        if len(dirname) > 30:
            dirname = dirname[:30]
        dirname = helper.clean_filepath(dirname)
        
        # Create file path
        file_path = os.path.join("claims", dirname, filename)

        # avoid overwriting existing files
        if os.path.exists(file_path):
            print(f"Warning: claim file with name : {file_path} already exists", file=sys.stderr)
            continue
        
        # Write claim_doc to YAML file
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(claim_doc, f, default_flow_style=False, allow_unicode=True, width=float('inf'))
        
        print(f"Created claim document: {file_path}")

def main():
    claims_dir = os.path.join(os.path.dirname(__file__), "..", "claims")
    claims_dir = os.path.abspath(claims_dir)
    all_claim_docs = get_claim_docs(claims_dir)

    sources = helper.get_sources(API_KEY, API_BASE_URL)
    if sources is None:
        print(f"Error: failed to fetch all sources", file=sys.stderr)
        sys.exit(1)

    # Fetch falsifiable claim skill
    try:
        falsifiable_claim_skill = helper.get_text_from_url(FALSIFIABLE_CLAIM_SKILL_URL)
    except Exception as e:
        print(f"Error: failed to fetch skill from {FALSIFIABLE_CLAIM_SKILL_URL}: {e}", file=sys.stderr)
        sys.exit(1)

    for source in sources:
        domain_url = source["uri"]
        if source["domainUrlNewsData"] != "":
            domain_url = source["domainUrlNewsData"]
        else:
            helper.patch_sources(API_KEY, API_BASE_URL, source["uriDigest"], {"domainUrlNewsData": domain_url})
            
        claims = newsdata_io.get_claims(domain_url)
        if claims is None or len(claims) == 0:
            continue

        # keep only those articles that can be classified as falsifiable claims
        req_content = (
            "Following is a list of 10 articles published by the same news outlet. Each article is represented by a json string type element in the array"
            f"\n\n{claims}\n\n"
            f"{CLAIM_FILTER_PROMPT}"
        )
        filtered_claims = openrouter.req_w_addons(req_content, skill=falsifiable_claim_skill, tools=[openrouter.WEB_SEARCH_TOOL])
        if filtered_claims == "":
            print(f"Error: failed to filter claims for source {source['name']}", file=sys.stderr)
            continue
        
        try:
            filtered_claims_list = json.loads(helper.cleanup_json_str(filtered_claims))
        except Exception as e:
            print(f"Error: failed to cleanup and unmarshal claims json string {filtered_claims}: {e}", file=sys.stderr)
            continue

        if len(filtered_claims_list) == 0:
            print(f"Error: no claims found for {source['name']} in: {filtered_claims}", file=sys.stderr)
            continue

        # list of new claims to be ingested
        new_unique_claims = get_new_claims(all_claim_docs, filtered_claims_list, source["uriDigest"])        
        create_claim_docs(new_unique_claims, source["name"])
    
if __name__ == "__main__":
    sys.exit(main())
