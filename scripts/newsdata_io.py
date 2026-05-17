#!/usr/bin/env python3

import glob
import demjson3
import json
import os
import re
import sys
import time
from typing import Tuple
from urllib.request import Request, urlopen
import requests
import yaml

# Query parameters constants
CATEGORY = "environment,technology,world"
LANGUAGE = "en"
REMOVE_DUPLICATE = "1"
SIZE = "10"
DATATYPE = "news,research,analysis,pressRelease"

FALSIFIABLE_CLAIM_SKILL_URL = "https://raw.githubusercontent.com/semmet95/agent-skills/refs/heads/main/determine-falsifialbe-claim/SKILL.md"
CLAIM_PER_SOURCE = 2
# FREE_MODELS_DOC = [
#     "openai/gpt-oss-120b",
#     "mistralai/mistral-medium-3-5",
#     "moonshotai/kimi-k2-0905",
#     "google/gemma-4-31b-it:free",
#     "qwen/qwen3-32b",
#     "google/gemini-3.1-flash-lite",
#     "deepseek/deepseek-v4-flash:free",
#     "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
#     "cohere/command-a"
# ]

FREE_MODELS_DOC = [
    "embercloud/glm-4.7-flash",
    "zai/glm-4.7-flash",
    "zai/glm-4.6v-flash",
    "zai/glm-4.5-flash"
]


def fetch_web_text(url: str) -> str:
    with urlopen(url, timeout=10) as r:
        return r.read().decode("utf-8")

def get_sources(base_url: str, api_key: str):
    endpoint = f"{base_url}/api/v1/sources"
    headers = {"X-API-Key": api_key}
    response = requests.get(endpoint, headers=headers, timeout=90)
    if response.status_code != 200:
        print(f"Error: Received status code {response.status_code}")
        exit(1)
    return response.json()

def post_openrouter(base_url: str, api_key: str, payload: dict) -> Tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        f"{base_url}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    status = -1
    try:
        with urlopen(req, timeout=120) as r:
            status = r.getcode()
            body = r.read().decode("utf-8")
    except Exception as e:
        print(f"Error making request to OpenRouter API: {e}", file=sys.stderr)
        body = ""

    return status, body

def req_openrouter(base_url: str, api_key: str, payload: dict) -> str:
    status, body = post_openrouter(base_url, api_key, payload)

    if status == 200:
        try:
            data = json.loads(body)
        except Exception as e:
            print(f"Failed to parse JSON response: {e}", file=sys.stderr)
            print(body)
            return ""

        # Extract assistant reply
        reply = None
        try:
            reply = data["choices"][0]["message"]["content"]
            return reply
        except Exception as e:
            print(f"Failed to access key [choices][0][message][content]: {e}", file=sys.stderr)
            return ""
    else:
        print(f"Openrouter response status: {status}", file=sys.stderr)
        return ""

def filter_claims(base_url: str, api_key: str, falsifiable_claim_skill: str, claims):
    filter_prompt = (
        "Following is a list of 10 articles published by the same news outlet. Each article is represented by a json string type element in the array\n\n"
        f"{claims}"
        "\n\nUse web search tool to visit the link for each article, access the content and then assess if it is a falsifiable claim."
        "\nOut of these 10 articles, only return the 2 article that best fit the falsifiable claim criterion."
        "Prefer claims that have been made by the news source directly"
        "Keep the json structure of the claims the same as the input. Do not add or remove any field."
        "Only output the plain json array string that I can safely unmarshal."
        "Do not format the string. Do not output anything else."
    )

    filtered_claims = ""
    filtered_claims_list = []
    ctr = 1
    for model in FREE_MODELS_DOC:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": falsifiable_claim_skill},
                {
                    "role": "user",
                    "content": filter_prompt
                },
            ],
            # "tools": [
            #     # {"type": "openrouter:web_search"}
            #     {"type": "web_search"}
            # ]
        }

        filtered_claims = req_openrouter(base_url, api_key, payload)
        if filtered_claims != None and filtered_claims != "":
            # models often return the json string wrapped in a code block or with incompatible values            
            filtered_claims = filtered_claims.replace("'", '"')
            # Replace all Python boolean and None values
            filtered_claims = re.sub(r':\s*None\b', ': null', filtered_claims)
            filtered_claims = re.sub(r':\s*False\b', ': false', filtered_claims)
            filtered_claims = re.sub(r':\s*True\b', ': true', filtered_claims)
            
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', filtered_claims, re.DOTALL)
            if match:
                filtered_claims = match.group(1)
            try:
                filtered_claims = filtered_claims.replace("`", "'")
                filtered_claims = json.dumps(demjson3.decode(filtered_claims))
                filtered_claims_list = json.loads(filtered_claims)
            except Exception as e:
                print(f"Error: failed to unmarshal claims json string {filtered_claims}: {e}", file=sys.stderr)
                continue
            break

        # delay before sending the request again
        time.sleep(30*ctr)
        ctr += 1

    if filtered_claims_list == None or len(filtered_claims_list) == 0:
        print("Error: All models failed.", file=sys.stderr)
        sys.exit(1)
    
   
    return filtered_claims_list

def get_claims(base_url: str, api_key: str, src_domain_url: str):
    endpoint = f"{base_url}/latest"
    params = {
        "category": CATEGORY,
        "language": LANGUAGE,
        "removeduplicate": REMOVE_DUPLICATE,
        "size": SIZE,
        "datatype": DATATYPE,
        "apikey": api_key,
        "domainurl": src_domain_url
    }
    response = requests.get(endpoint, params=params, timeout=10)
    if response.status_code != 200:
        print(f"Error: couldn't fetch claims for {src_domain_url}: {response.status_code}")
        return None
    return response.json()["results"]

def update_claim_fields(srcDigest: str, claim):
    claim["sourceUriDigest"] = srcDigest
    claim["summary"] = claim["description"]
    claim["uri"] = claim["link"]

def get_claim_docs():
    claims_dir = os.path.join(os.path.dirname(__file__), "..", "claims")
    claims_dir = os.path.abspath(claims_dir)
    
    # Find all YAML files in claims directory and subdirectories
    yaml_files = glob.glob(os.path.join(claims_dir, "**", "*.yaml"), recursive=True)
    yaml_files.extend(glob.glob(os.path.join(claims_dir, "**", "*.yml"), recursive=True))
    
    claims_array = []
    for yaml_file in yaml_files:
        try:
            with open(yaml_file, 'r') as f:
                claim_data = yaml.safe_load(f)
                if claim_data:  # Only add if file is not empty
                    claims_array.append(claim_data)
        except Exception as e:
            print(f"Error loading YAML file {yaml_file}: {e}", file=sys.stderr)
    
    return claims_array

def is_claim_new(claim) -> bool:
    claim_docs = get_claim_docs()

    for claim_doc in claim_docs:
        if claim["uri"] == claim_doc["uri"] or claim["title"] == claim_doc["title"]:
            return False

    return True

def clean_filepath(path: str, replace: str = "_") -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_-]', replace, path)
    cleaned = re.sub(f'{re.escape(replace)}+', replace, cleaned)
    cleaned = cleaned.strip(replace)
    return cleaned

def create_claim_docs(claims: list, srcName: str):
    with open('oapi.yaml', 'r') as f:
        oapi_spec = yaml.safe_load(f)

    claim_input_schema = oapi_spec['components']['schemas']['ClaimInput']
    claim_example = claim_input_schema.get('example')

    # Custom representer to force double quotes around strings
    def quoted_str_representer(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')
    
    yaml.add_representer(str, quoted_str_representer)

    for claim in claims:
        claim_doc = {}
        for key in claim_example.keys():
            claim_doc[key] = str(claim[key])
        
        filename = claim_doc["title"].lower()
        if len(filename) > 30:
            filename = filename[:30]
        filename = clean_filepath(filename)
        filename = f"{filename}.yaml"

        dirname = srcName.lower()
        if len(dirname) > 30:
            dirname = dirname[:30]
        dirname = clean_filepath(dirname)
        
        # Create file path
        file_path = os.path.join("claims", dirname, filename)
        
        # Write claim_doc to YAML file
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(claim_doc, f, default_flow_style=False, allow_unicode=True, width=float('inf'))
        
        print(f"Created claim document: {file_path}")

def main():
    base_url = os.environ["API_BASE_URL"]
    api_key = os.environ["API_KEY"]
    news_data_base_url = os.environ["NEWSDATA_API_BASE_URL"]
    news_data_api_key = os.environ["NEWSDATA_API_KEY"]
    # openrouter_api_key = os.environ["OPENROUTER_API_KEY"]
    # openrouter_base_url = os.environ["OPENROUTER_API_BASE_URL"]
    openrouter_api_key = os.environ["LLM_GATEWAY_API_KEY"]
    openrouter_base_url = "https://api.llmgateway.io/v1"

    sources = get_sources(base_url, api_key)

    # Fetch falsifiable claim skill
    try:
        falsifiable_claim_skill = fetch_web_text(FALSIFIABLE_CLAIM_SKILL_URL)
    except Exception as e:
        print(f"Error: failed to fetch skill from {FALSIFIABLE_CLAIM_SKILL_URL}: {e}", file=sys.stderr)
        sys.exit(1)

    src_to_patch = set()
    for source in sources:
        domain_url = source["uri"]
        if source["domainUrlNewsData"] != "":
            domain_url = source["domainUrlNewsData"]
        else:
            src_to_patch.add(source["uriDigest"])
            
        claims = get_claims(news_data_base_url, news_data_api_key, domain_url)
        if claims == None:
            continue

        # keep only those articles that can be classified as falsifiable claims
        filtered_claims = filter_claims(openrouter_base_url, openrouter_api_key, falsifiable_claim_skill, claims)
        
        # list of new claims to be ingested
        new_claims = []
        # keep only relevant fields in the claims
        for claim in filtered_claims:
            update_claim_fields(source["uriDigest"], claim)
            if is_claim_new(claim):
                new_claims.append(claim)
        
        create_claim_docs(new_claims, source["name"])
    
if __name__ == "__main__":
    sys.exit(main())