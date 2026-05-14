#!/usr/bin/env python3

import json
import os
import re
import sys
from typing import Tuple
from urllib.request import Request, urlopen
import requests

# Query parameters constants
CATEGORY = "environment,technology,world"
LANGUAGE = "en"
REMOVE_DUPLICATE = "1"
SIZE = "10"
DATATYPE = "news,research,analysis,pressRelease"

FALSIFIABLE_CLAIM_SKILL_URL = "https://raw.githubusercontent.com/semmet95/agent-skills/refs/heads/main/determine-falsifialbe-claim/SKILL.md"
CLAIM_PER_SOURCE = 2
FREE_MODELS_DOC = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "google/gemma-4-26b-a4b-it:free",
]

def fetch_web_text(url: str) -> str:
    with urlopen(url, timeout=60) as r:
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
        with urlopen(req, timeout=60) as r:
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

def filter_claims(base_url: str, api_key: str, falsifiable_claim_skill: str, claims):
    filter_prompt = (
        "Following is a list of 10 articles published by the same news outlet. Each article is represented by a json string type element in the array\n\n"
        f"{claims}"
        "\n\nUse web search tool to visit the link for each article, access the content and then assess if it is a falsifiable claim."
        "\nOut of these 10 articles, only return the 2 article that best fit the falsifiable claim criterion."
        "Prefer claims that have been made by the news source directly"
        "Keep the json structure of the claims the same as the input. Do not add or remove any field."
        "Only output the plain json array string that I can directly load into a Python dict."
        "Do not format the string. Do not output anything else."
    )

    filtered_claims = ""
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
            "tools": [
                {"type": "openrouter:web_search"}
            ]
        }

        filtered_claims = req_openrouter(base_url, api_key, payload)
        if filtered_claims != "":
            break

    if filtered_claims == "":
        print("Error: All models failed.", file=sys.stderr)
        sys.exit(1)
    
    # models often return the json string wrapped in a code block
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', filtered_claims, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    
    return json.loads(filtered_claims)

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
        print(f"Error: Received status code {response.status_code}")
        exit(1)
    return response.json()["results"]

    # filtered_claims = []
    # for claim in claims:
    #     filtered_claims.append({
    #         "uri": claim["claim"],
    #         "claimDate": claim["claimDate"],
    #         "claimReviewDate": claim["claimReviewDate"],
    #         "claimReviewRating": claim["claimReviewRating"],
    #         "claimReviewUrl": claim["claimReviewUrl"],
    #         "claimReviewPublisher": claim["claimReviewPublisher"],
    #     })

def update_claim_fields(srcDigest: str, claim):
    claim["sourceUriDigest"] = srcDigest
    claim["summary"] = claim["description"]
    claim["uri"] = claim["link"]

def main():
    base_url = os.environ["API_BASE_URL"]
    api_key = os.environ["API_KEY"]
    news_data_base_url = os.environ["NEWSDATA_API_BASE_URL"]
    news_data_api_key = os.environ["NEWSDATA_API_KEY"]
    openrouter_api_key = os.environ["OPENROUTER_API_KEY"]
    openrouter_base_url = os.environ["OPENROUTER_API_BASE_URL"]

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

        # keep only those articles that can be classified as falsifiable claims
        filtered_claims = filter_claims(openrouter_base_url, openrouter_api_key, falsifiable_claim_skill, claims)
        
        # keep only relevant fields in the claims
        for claim in filtered_claims:
            update_claim_fields(source["uriDigest"], claim)
        
        print(filtered_claims)
        break
    
if __name__ == "__main__":
    sys.exit(main())