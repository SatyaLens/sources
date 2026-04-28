#!/usr/bin/env python3
"""Validate request documents against OpenAPI schemas."""

import sys
import os
from pathlib import Path
import traceback
from referencing.jsonschema import DRAFT202012
from referencing import Registry, Resource

# Shared utilities (try package import first, fallback to local module)
try:
    from scripts.common import load_oapi, load_doc
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from common import load_oapi, load_doc

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

# folder -> schema $ref in oapi.yaml
SCHEMA_MAP = {
    "sources": "#/components/schemas/SourceInput",
    "claims": "#/components/schemas/ClaimInput",
    "proofs": "#/components/schemas/ProofInput",
}

def resolve_schema(spec: dict, ref: str) -> dict:
    assert ref.startswith("#/"), f"Invalid ref: {ref}"
    parts = ref[2:].split("/")
    current = spec
    for part in parts:
        current = current[part]
    return current

def validate(data: dict, schema: dict, spec: dict) -> list[str]:
    registry = Registry().with_resource(
        "oapi",
        Resource.from_contents(spec, DRAFT202012)  # explicit spec
    )
    validator = Draft202012Validator(schema, registry=registry)
    return [f"{e.json_path}: {e.message}" for e in validator.iter_errors(data)]

def scan_tracked_files() -> list[str]:
    files = []
    for folder in SCHEMA_MAP:
        if not Path(folder).exists():
            continue
        for ext in ("*.yaml", "*.yml", "*.json"):
            files.extend(Path(folder).rglob(ext))
    return [str(f) for f in sorted(files)]


def _info(msg: str, *args) -> None:
    print("INFO:", msg % args if args else msg)


def _error(msg: str, *args) -> None:
    print("ERROR:", msg % args if args else msg, file=sys.stderr)


def _exception(msg: str, *args) -> None:
    print("ERROR:", msg % args if args else msg, file=sys.stderr)
    traceback.print_exc(file=sys.stderr)

def main() -> int:
    files = sys.argv[1:]

    if not files:
        _info("Validating new docs...")
        files = scan_tracked_files()

    spec = load_oapi("oapi.yaml")
    failed = False

    _info("Validation run: %d file(s) to check", len(files))

    for f in files:
        f = f.strip()
        if not f:
            continue

        _info("Validating %s", f)

        parts = Path(f).parts
        if not parts or parts[0] not in SCHEMA_MAP:
            continue

        folder = parts[0]
        schema_ref = SCHEMA_MAP[folder]
        schema = resolve_schema(spec, schema_ref)

        if not Path(f).exists():
            _error("%s: File not found", f)
            failed = True
            continue

        try:
            data = load_doc(f)
        except Exception as e:
            _exception("%s: Failed to parse document: %s", f, e)
            failed = True
            continue

        errors = validate(data, schema, spec)
        if errors:
            _error("%s: %d validation error(s)", f, len(errors))
            for e in errors:
                _error("   - %s", e)
            failed = True
        else:
            _info("%s: OK", f)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())