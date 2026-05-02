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

# Use jsonschema's Draft202012Validator for validation
from jsonschema import Draft202012Validator

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
    # Use jsonschema validator directly. The referencing-based registry
    # approach was causing incompatibilities in some environments, so
    # stick to the standard validator here and produce readable paths.
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for e in validator.iter_errors(data):
        # Build a JSON-path-like representation from the error path
        if hasattr(e, 'path') and e.path:
            path = '/'.join(str(p) for p in e.path)
        else:
            path = '<root>'
        errors.append(f"{path}: {e.message}")
    return errors


def _parse_validate_rules(s: str) -> list[str]:
    if not s:
        return []
    if isinstance(s, str):
        return [p.strip() for p in s.split(',') if p.strip()]
    if isinstance(s, (list, tuple)):
        return list(s)
    return []


def run_extra_validations(data: dict, schema: dict) -> list[str]:
    """Run x-oapi-codegen-extra-tags validators declared in the schema.

    Supported validators: nonempty, nospace, httpsurl
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return errors

    props = schema.get('properties') or {}
    for name, prop_schema in props.items():
        extra = prop_schema.get('x-oapi-codegen-extra-tags') or {}
        validate_spec = extra.get('validate') if isinstance(extra, dict) else None
        rules = _parse_validate_rules(validate_spec) # type: ignore
        if not rules:
            continue

        # Skip missing fields; JSON Schema required/nullable rules will cover requiredness
        if name not in data:
            continue

        val = data.get(name)

        for rule in rules:
            if rule == 'nonempty':
                if val is None:
                    errors.append(f"{name}: must not be empty")
                elif isinstance(val, str) and len(val.strip()) == 0:
                    errors.append(f"{name}: must not be empty")
                elif isinstance(val, (list, dict)) and len(val) == 0:
                    errors.append(f"{name}: must not be empty")

            elif rule == 'nospace':
                if val is None:
                    continue
                if not isinstance(val, str):
                    errors.append(f"{name}: nospace rule applies to string values")
                elif ' ' in val:
                    errors.append(f"{name}: must not contain spaces")

            elif rule == 'httpsurl':
                if not isinstance(val, str) or not val.startswith('https://'):
                    errors.append(f"{name}: must be an https URL")

            # Unknown rules are ignored for now

    return errors

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
        # Run extra validators defined via x-oapi-codegen-extra-tags
        extra_errors = run_extra_validations(data, schema)
        if extra_errors:
            errors.extend(extra_errors)

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