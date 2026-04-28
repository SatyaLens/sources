#!/usr/bin/env python3
"""POST newly added request documents to their respective APIs.

Requires environment variables:
    API_BASE_URL    API server base URL
    API_KEY         API token for authentication
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Shared utilities (try package import first, fallback to local module)
try:
    from scripts.common import load_oapi, load_doc
except Exception:
    sys.path.insert(0, os.path.dirname(__file__))
    from common import load_oapi, load_doc

# folder -> schema name
SCHEMA_MAP = {
    "sources": "SourceInput",
    "claims": "ClaimInput",
    "proofs": "ProofInput",
}

def extract_post_paths(spec: dict) -> dict[str, str]:
    """Map schema names to path suffixes from the OpenAPI spec."""
    paths = {}
    for path, methods in spec.get("paths", {}).items():
        post = methods.get("post")
        if not post:
            continue

        content = post.get("requestBody", {}).get("content", {})
        json_schema = content.get("application/json", {}).get("schema", {})
        ref = json_schema.get("$ref", "")

        if ref.startswith("#/components/schemas/"):
            schema_name = ref.split("/")[-1]
            paths[schema_name] = path

    return paths

def post(url: str, data: dict, api_key: str) -> tuple[int, str]:
    payload = json.dumps(data).encode()
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": f"{api_key}",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main() -> int:
    base_url = os.environ.get("API_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("API_KEY", "")

    if not base_url:
        print("API_BASE_URL environment variable is not set", file=sys.stderr)
        return 1
    if not api_key:
        print("API_KEY environment variable is not set", file=sys.stderr)
        return 1

    files = [f for f in os.environ.get("ADDED_FILES", "").splitlines() if f.strip()]
    if not files:
        print("No added files to process.")
        return 0

    spec = load_oapi("oapi.yaml")
    schema_paths = extract_post_paths(spec)

    failed = False
    for f in files:
        f = f.strip()
        parts = Path(f).parts
        if not parts or parts[0] not in SCHEMA_MAP:
            continue

        folder = parts[0]
        schema_name = SCHEMA_MAP[folder]
        path = schema_paths.get(schema_name)
        if not path:
            print(f"No POST path found for schema {schema_name}, skipping {f}")
            failed = True
            continue

        url = f"{base_url}{path}"

        if not Path(f).exists():
            print(f"{f}: File not found")
            failed = True
            continue

        try:
            data = load_doc(f)
        except Exception as e:
            print(f"{f}: Failed to parse: {e}")
            failed = True
            continue

        status, body = post(url, data, api_key)
        if 200 <= status < 300:
            print(f"{f} → {url} ({status})")
        else:
            print(f"{f} → {url} ({status}): {body[:200]}")
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())