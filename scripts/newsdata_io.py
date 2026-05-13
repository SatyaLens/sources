#!/usr/bin/env python3

import os
import sys
import requests

# Query parameters constants
CATEGORY = "environment,technology,world"
LANGUAGE = "en"
REMOVE_DUPLICATE = "1"
SIZE = "10"
DATATYPE = "news,research,analysis,pressRelease"

def get_sources(base_url: str, api_key: str):
    endpoint = f"{base_url}/api/v1/sources"
    headers = {"X-API-Key": api_key}
    response = requests.get(endpoint, headers=headers, timeout=90)
    if response.status_code != 200:
        print(f"Error: Received status code {response.status_code}")
        exit(1)
    return response.json()

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
    return response.json()

def main():
    base_url = os.environ["API_BASE_URL"]
    api_key = os.environ["API_KEY"]
    news_data_base_url = os.environ["NEWSDATA_API_BASE_URL"]
    news_data_api_key = os.environ["NEWSDATA_API_KEY"]

    sources = get_sources(base_url, api_key)
    src_to_patch = set()
    for source in sources:
        domain_url = source["uri"]
        if source["domainUrlNewsData"] != "":
            domain_url = source["domainUrlNewsData"]
        else:
            src_to_patch.add(source["uriDigest"])
            
        claims = get_claims(news_data_base_url, news_data_api_key, domain_url)
        print(claims)
        break
    
if __name__ == "__main__":
    sys.exit(main())