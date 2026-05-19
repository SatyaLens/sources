#!/usr/bin/env python3

import os
import requests

# Query parameters constants
CATEGORY = "environment,technology,world"
LANGUAGE = "en"
REMOVE_DUPLICATE = "1"
SIZE = "10"
DATATYPE = "news,research,analysis,pressRelease"

NEWSDATA_API_BASE_URL = os.getenv("NEWSDATA_API_BASE_URL", "https://newsdata.io/api/1")
NEWSDATA_API_KEY = os.environ["NEWSDATA_API_KEY"]

def get_claims(src_domain_url: str):
    endpoint = f"{NEWSDATA_API_BASE_URL}/latest"
    params = {
        "category": CATEGORY,
        "language": LANGUAGE,
        "removeduplicate": REMOVE_DUPLICATE,
        "size": SIZE,
        "datatype": DATATYPE,
        "apikey": NEWSDATA_API_KEY,
        "domainurl": src_domain_url
    }
    response = requests.get(endpoint, params=params, timeout=10)
    if response.status_code != 200:
        print(f"Error: couldn't fetch claims for {src_domain_url}: {response.status_code}")
        resp_body = response.json()
        if resp_body.get("results") is not None and resp_body.get("results").get("suggestion") is not None:
            print(f"Suggested domain url(s) for {src_domain_url}: {resp_body['results']['suggestion']}")
        return None
    return response.json()["results"]
