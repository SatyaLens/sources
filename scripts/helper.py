#!/usr/bin/env python3
"""Helper functions for scripts"""

import json
import os
import sys
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
        return -1, ""

    return status, body
