#!/usr/bin/env python3
"""Validate request documents against OpenAPI schemas."""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

# folder -> schema $ref in openapi.yaml
SCHEMA_MAP = {
    "sources": "#/components/schemas/SourceInput",
    "claims": "#/components/schemas/AdmissionRequest",
    "proofs": "#/components/schemas/AdmissionRequest",
}

def load_oapi(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

def resolve_schema(spec: dict, ref: str) -> dict:
    assert ref.startswith("#/"), f"Invalid ref: {ref}"
    parts = ref[2:].split("/")
    current = spec
    for part in parts:
        current = current[part]
    return current

def load_doc(path: str) -> dict:
    with open(path) as f:
        content = f.read()
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError:
        return json.loads(content)

def validate(data: dict, schema: dict, spec: dict) -> list[str]:
    registry = Registry().with_resource("oapi", Resource.from_contents(spec)) # type: ignore
    validator = Draft202012Validator(schema, registry=registry)
    return [f"{e.json_path}: {e.message}" for e in validator.iter_errors(data)]

def scan_tracked_files() -> list[str]:
    files = []
    for folder in SCHEMA_MAP:
        if not Path(folder).exists():
            continue
        for ext in ("*.yaml", "*.yml", "*.json"):
            files.extend(Path(folder).glob(ext))
    return [str(f) for f in sorted(files)]

def main() -> int:
    files = sys.argv[1:]
    if not files:
        print("Validating all files...")
        files = scan_tracked_files()
        return 0

    spec = load_oapi("oapi.yaml")
    failed = False

    for f in files:
        f = f.strip()
        if not f:
            continue

        parts = Path(f).parts
        if not parts or parts[0] not in SCHEMA_MAP:
            continue

        folder = parts[0]
        schema_ref = SCHEMA_MAP[folder]
        schema = resolve_schema(spec, schema_ref)

        if not Path(f).exists():
            print(f"{f}: File not found")
            failed = True
            continue

        try:
            data = load_doc(f)
        except Exception as e:
            print(f"{f}: Failed to parse document: {e}")
            failed = True
            continue

        errors = validate(data, schema, spec)
        if errors:
            print(f"{f}:")
            for e in errors:
                print(f"   - {e}")
            failed = True
        else:
            print(f"{f}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())