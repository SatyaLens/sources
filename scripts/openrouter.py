#!/usr/bin/env python3
"""OpenRouter helper: try multiple models until one returns HTTP 200 and print assistant reply.

Usage:
  python3 scripts/openrouter.py path/to/page.md

Environment:
  OPENROUTER_API_KEY must be set.
"""

import json
import os
import sys
import time

import helper

FREE_MODELS_DOC = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "openrouter/free"
]
WEB_SEARCH_TOOL = {"type": "openrouter:web_search"}

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
MD_PROCESSING_SKILL_URL = os.getenv("MD_PROCESSING_SKILL_URL", "https://raw.githubusercontent.com/semmet95/agent-skills/refs/heads/main/md-processing/SKILL.md")
OPENROUTER_CHAT_ENDPOINT = os.getenv("OPENROUTER_CHAT_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_MAX_RETRIES = int(os.getenv("OPENROUTER_MAX_RETRIES", "3"))

def req_chat(payload: dict) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    for i in range(1, OPENROUTER_MAX_RETRIES + 1):
        status, body = helper.post_request(
            OPENROUTER_CHAT_ENDPOINT,
            headers,
            payload,
            180,
        )

        if status == 0 or status == 429 or 500 <= status < 600:
            print(f"OpenRouter API returned status {status}, retrying...", file=sys.stderr)
            time.sleep(10 * i)
            continue

        if status == 200:
            try:
                data = json.loads(body)
            except Exception as e:
                print(f"Failed to parse openrouter json response {body}: {e}", file=sys.stderr)
                return ""

            # Extract assistant reply
            try:
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"Failed to access key [choices][0][message][content] in json {data}: {e}", file=sys.stderr)
                return ""
        else:
            print(f"Openrouter response status: {status} with bode: {body}", file=sys.stderr)
            break

    return ""

def req_w_addons(content: str, skill="", tools=[]) -> str:
    resp = ""
    for model in FREE_MODELS_DOC:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": content
                },
            ],
        }

        if skill != "":
            payload["messages"].append({"role": "system", "content": skill})

        if len(tools) > 0:
            payload["tools"] = tools
        
        resp = req_chat(payload)
        if resp != "":
            break
        print(f"{model} failed, retrying with another model...")

    if resp == "":
        print("Error: All models failed.", file=sys.stderr)

    return resp
