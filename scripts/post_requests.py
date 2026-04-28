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
import traceback

# Shared utilities (try package import first, fallback to local module)
try:
    from scripts.common import load_oapi, load_doc
except ImportError:
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

def post(url: str, data: dict, api_key: str, timeout: float = 90.0) -> tuple[int, str]:
    payload = json.dumps(data).encode()
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except urllib.error.URLError as e:
        # Covers timeouts, DNS failures, refused connections, etc.
        reason = str(e.reason)
        return 0, reason


def main() -> int:
    def _info(msg: str, *args) -> None:
        print("INFO:", msg % args if args else msg)

    def _error(msg: str, *args) -> None:
        print("ERROR:", msg % args if args else msg, file=sys.stderr)

    def _exception(msg: str, *args) -> None:
        print("ERROR:", msg % args if args else msg, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    base_url = os.environ.get("API_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("API_KEY", "")

    if not base_url:
        _error("API_BASE_URL environment variable is not set")
        return 1
    if not api_key:
        _error("API_KEY environment variable is not set")
        return 1

    files = [f for f in os.environ.get("ADDED_FILES", "").splitlines() if f.strip()]
    if not files:
        _info("No added files to process.")
        return 0

    _info("POST run: %d file(s) to process", len(files))

    spec = load_oapi("oapi.yaml")
    schema_paths = extract_post_paths(spec)

    failed = False
    allowed_exts = {".yaml", ".yml", ".json"}
    for f in files:
        f = f.strip()
        if not f:
            continue

        # normalize path parts (skip '.' and '..')
        p = Path(f)
        parts = [part for part in p.parts if part not in (".", "..")]
        if not parts:
            continue

        folder = parts[0]
        if folder not in SCHEMA_MAP:
            continue

        norm_path = Path(*parts)
        if norm_path.suffix.lower() not in allowed_exts:
            _info("Skipping non-document file: %s", str(norm_path))
            continue

        schema_name = SCHEMA_MAP[folder]
        path = schema_paths.get(schema_name)
        if not path:
            _error("No POST path found for schema %s, skipping %s", schema_name, str(norm_path))
            failed = True
            continue

        url = f"{base_url}{path}"
        # warn if BASE_URL likely duplicates path prefix (common misconfiguration)
        path_segments = [seg for seg in path.split("/") if seg]
        if path_segments and base_url.rstrip("/").endswith("/" + path_segments[0]):
            _info("Warning: BASE_URL '%s' may duplicate path segment '%s' when combined with '%s'", base_url, path_segments[0], path)

        if not norm_path.exists():
            _error("%s: File not found", str(norm_path))
            failed = True
            continue

        try:
            data = load_doc(str(norm_path))
        except Exception as e:
            _exception("%s: Failed to parse: %s", str(norm_path), e)
            failed = True
            continue

        if not isinstance(data, dict):
            _error("%s: Parsed document is not a JSON object; skipping", str(norm_path))
            failed = True
            continue

        _info("Posting %s -> %s", str(norm_path), url)
        try:
            status, body = post(url, data, api_key)
        except Exception as e:
            _exception("%s: Request failed: %s", str(norm_path), e)
            failed = True
            continue

        if 200 <= status < 300:
            _info("%s → %s (%d)", str(norm_path), url, status)
        else:
            _error("%s → %s (%d): %s", str(norm_path), url, status, body[:200])
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())