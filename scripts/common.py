#!/usr/bin/env python3
"""Shared utilities for scripts in this folder.

Exports:
- load_oapi(path) -> dict
- load_doc(path) -> dict (YAML with JSON fallback)
"""

from pathlib import Path
import json
import yaml
from typing import Any, Dict


def load_oapi(path: str) -> Dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f)


def load_doc(path: str) -> Dict[str, Any]:
    with open(path) as f:
        content = f.read()
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError:
        return json.loads(content)
