#!/usr/bin/env python3
"""Helper functions for scripts"""

import json
import demjson3
import os
import re
import sys
import requests
import yaml
from typing import Tuple
from urllib.request import Request, urlopen

def get_text_from_url(url: str) -> str:
    with urlopen(url, timeout=60) as r:
        return r.read().decode("utf-8")

def get_text_from_file(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def get_oapi_spec():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    oapi_path = os.path.join(base_dir, "oapi.yaml")
    
    with open(oapi_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_sources(base_url: str, api_key: str):
    endpoint = f"{base_url}/api/v1/sources"
    headers = {"X-API-Key": api_key}
    response = requests.get(endpoint, headers=headers, timeout=90)
    if response.status_code != 200:
        print(f"Error: failed to get all sources: {response.status_code}")
        return None
    return response.json()

def cleanup_json_str(json_str: str) -> str:
    # models often return the json string wrapped in a code block or with incompatible values
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', json_str, re.DOTALL)
    if match:
        json_str = match.group(1)

    # Replace all Python boolean and None values
    json_str = re.sub(r':\s*None\b', ': null', json_str)
    json_str = re.sub(r':\s*False\b', ': false', json_str)
    json_str = re.sub(r':\s*True\b', ': true', json_str)

    json_str = json_str.replace("`", "'")
    json_str = json_str.strip().replace("'", "\'")
    json_str = json.dumps(demjson3.decode(json_str))

    return json_str

def clean_filepath(path: str, replace: str = "_") -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_-]', replace, path)
    cleaned = re.sub(f'{re.escape(replace)}+', replace, cleaned)
    cleaned = cleaned.strip(replace)
    return cleaned

def post_request(endpoint: str, headers: dict, payload: dict, timeout: int) -> Tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url=endpoint,
        data=data,
        headers=headers
    )

    try:
        with urlopen(req, timeout=timeout) as r:
            status = r.getcode()
            body = r.read().decode("utf-8")
    except Exception as e:
        print(f"Error making request to {endpoint}: {e}", file=sys.stderr)
        return 0, ""

    return status, body
