#!/usr/bin/env python3

import glob
import json
import os
import requests
import sys
import yaml
from urllib.parse import urlparse

import helper
import openrouter

API_BASE_URL = os.environ["API_BASE_URL"]
API_KEY = os.environ["API_KEY"]

MAX_PROOF_COUNT = int(os.getenv("MAX_PROOF_COUNT", "3"))
CLAIM_VERIFICATION_SKILL_URL = os.getenv(
    "CLAIM_VERIFICATION_SKILL_URL",
    "https://raw.githubusercontent.com/semmet95/agent-skills/refs/heads/main/claim-verification/SKILL.md"
)
CLAIM_VERIFICATION_PROMPT = os.getenv(
    "CLAIM_VERIFICATION_PROMPT",
    (
        "Use web search tool to access the claim link, fetch the content and process it."
        "Use the web search tool again to look for proofs in the form of official statements, press releases, or reports from reputable sources to prove the claim right or wrong conclusively"
        "Ensure that the proofs belong to the same timeline as the claim. Do not include proofs that have similar description as the claim but is old or outdated."
        "Output links to the 2 sources that prove the claim right or wrong and specify as a boolean whether they support the claim or not"
        "The output format should be a json array with each element being a json object corresponding to a source supporting or refuting the claim"
        "Each json element should follow the following schema: {\"uri\": \"string\",  \"supports_claim\": boolean}"
    )
)

def get_proof_docs(proofs_dir: str):
    # Find all YAML files in claims directory and subdirectories
    yaml_files = glob.glob(os.path.join(proofs_dir, "**", "*.yaml"), recursive=True)
    yaml_files.extend(glob.glob(os.path.join(proofs_dir, "**", "*.yml"), recursive=True))

    proofs_array = []
    for yaml_file in yaml_files:
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                proof_data = yaml.safe_load(f)
                if proof_data:  # Only add if file is not empty
                    proofs_array.append(proof_data)
        except Exception as e:
            print(f"Error loading YAML file {yaml_file}: {e}", file=sys.stderr)
    
    return proofs_array

def get_new_proofs(all_proof_docs, new_proofs):
    unique_proofs = []

    for proof in new_proofs:
        new_proof = True
        for proof_doc in all_proof_docs:
            if proof["uri"] == proof_doc["uri"]:
                new_proof = False
                break
        if new_proof:
            unique_proofs.append(proof)

    return unique_proofs

def create_proof_docs(proofs: list, claim_name: str, claim_uri_digest: str):
    proof_input_schema = helper.get_oapi_spec()['components']['schemas']['ProofInput']
    proof_example = proof_input_schema.get('example')

    # Custom representer to force double quotes around strings
    def quoted_str_representer(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')
    yaml.add_representer(str, quoted_str_representer)

    for proof in proofs:
        # verify proof link is valid
        proof_uri = proof.get("uri")
        try:
            response = requests.get(proof_uri, timeout=30)
        except requests.RequestException as e:
            print(f"Warning: skipping proof with invalid uri {proof_uri}: {e}", file=sys.stderr)
            continue
        if response.status_code == 404:
            print(f"Warning: skipping proof with invalid uri {proof_uri}", file=sys.stderr)
            continue

        proof_doc = {
            "claimUriDigest": claim_uri_digest,
            "supportsClaim": proof["supports_claim"],
            "reviewedBy": "semmet95",
            "uri": proof_uri,
        }

        hostname = urlparse(proof_uri).hostname
        filename = hostname.lower().replace(".", "_")

        if len(filename) > 30:
            filename = filename[:30]
        filename = helper.clean_filepath(filename)
        filename = f"{filename}.yaml"

        dirname = claim_name.lower()
        if len(dirname) > 30:
            dirname = dirname[:30]
        dirname = helper.clean_filepath(dirname)
        
        # Create file path
        file_path = os.path.join("proofs", dirname, filename)

        # avoid overwriting existing files
        if os.path.exists(file_path):
            print(f"Warning: proof file with name : {file_path} already exists", file=sys.stderr)
            continue
        
        # Write proof_doc to YAML file
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(proof_doc, f, default_flow_style=False, allow_unicode=True, width=float('inf'))
        
        print(f"Created proof document: {file_path}")

def main():
    proofs_dir = os.path.join(os.path.dirname(__file__), "..", "proofs")
    proofs_dir = os.path.abspath(proofs_dir)
    all_proof_docs = get_proof_docs(proofs_dir)

    all_claims = helper.get_claims(API_KEY, API_BASE_URL)    
    if all_claims is None:
        print("Error: failed to fetch all claims", file=sys.stderr)
        sys.exit(1)

    # Fetch claim verification skill
    try:
        claim_verification_skill = helper.get_text_from_url(CLAIM_VERIFICATION_SKILL_URL)
    except Exception as e:
        print(f"Error: failed to fetch skill from {CLAIM_VERIFICATION_SKILL_URL}: {e}", file=sys.stderr)
        sys.exit(1)
    
    for claim in all_claims:
        if helper.is_claim_validated(API_KEY, API_BASE_URL, claim, MAX_PROOF_COUNT):
            print(f"max proofs already ingested for claim {claim["uri"]}, skipping...")
            continue

        print(f"fetching proofs for claim {claim["uri"]}")
        # get proofs that either support or deny the claim conclusively
        req_content = (
            "Following is a link to a falsifiable claim by a news media outlet as an article"
            f"\n\n{claim['uri']}\n\n"
            f"{CLAIM_VERIFICATION_PROMPT}"
        )
        claim_proofs = openrouter.req_w_addons(req_content, skill=claim_verification_skill, tools=[openrouter.WEB_SEARCH_TOOL])
        if claim_proofs == "":
            print(f"Error: failed to get proofs for claim {claim['uri']}", file=sys.stderr)
            continue
            
        try:
            claim_proofs_list = json.loads(helper.cleanup_json_str(claim_proofs))
        except Exception as e:
            print(f"Error: failed to cleanup and unmarshal proofs json string {claim_proofs}: {e}", file=sys.stderr)
            continue

        if len(claim_proofs_list) == 0:
            print(f"Error: no proofs found for {claim['uri']} in: {claim_proofs}", file=sys.stderr)
            continue

        # list of new proofs to be ingested
        new_unique_proofs = get_new_proofs(all_proof_docs, claim_proofs_list)
        create_proof_docs(new_unique_proofs, claim["title"], claim["uriDigest"])

if __name__ == "__main__":
    sys.exit(main())
