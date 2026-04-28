# AGENTS.md — Repository Guide for AI Assistants

## Repository Overview

This repository stores structured request documents organized by type. Each folder corresponds to a schema defined in `oapi.yaml`. All documents must conform to their folder's schema.

After merge to `main`, new documents are automatically POSTed to their respective API endpoints.

### Directory Layout

```text
.
├── oapi.yaml                    # Schemas + API endpoint paths
├── sources/                        # Source documents
├── claims/                         # Claims documents
├── proofs/                         # Proofs documents
├── scripts/
│   ├── validate.py                 # Validates documents against schemas
│   └── post_requests.py            # POSTs newly added documents to APIs
└── .github/workflows/
    ├── validate.yml                # Runs validate.py on PRs to main
    └── post_on_merge.yml           # Runs post_requests.py on push to main
```

## What the Validation Script Does

`scripts/validate.py` performs the following:

1. Loads `oapi.yaml` and extracts schemas from `components.schemas`.
2. Maps folders to schema names:
   - `sources/` → `SourceInput`
   - `claims/` → `ClaimInput`
   - `proofs/` → `ProofInput`
3. Scans each tracked folder for `.yaml`, `.yml`, and `.json` files.
4. Validates every found document against its corresponding schema using JSON Schema Draft 2020-12.
5. Reports pass/fail per file with specific field-level errors.

### Running Locally

```bash
# Validate all documents in tracked folders
python scripts/validate.py

# Validate specific files only
python scripts/validate.py sources/source1.yaml
```

## What the POST Script Does

`scripts/post_requests.py` performs the following:

1. Loads `oapi.yaml` and extracts API paths from the `paths` section.
2. Maps schema names to POST endpoints by matching `$ref` in `requestBody.content.application/json.schema`.
3. Reads the list of newly added files from the `ADDED_FILES` environment variable.
4. For each file:
   - Loads the YAML document.
   - Constructs the full URL as `API_BASE_URL + path` (e.g., `https://api.example.com/v1/source`).
   - POSTs the document as JSON with `X-API-Key: API_KEY`.
5. Reports pass/fail per file with HTTP status and response body.

### Environment Variables

| Variable | Required | Source |
|----------|----------|--------|
| `API_BASE_URL` | Yes | GitHub Secret `secrets.API_BASE_URL` |
| `API_KEY` | Yes | GitHub Secret `secrets.API_KEY` |
| `ADDED_FILES` | Yes | CI workflow computes this from `git diff` |

The script **exits with code 1 immediately** if `API_BASE_URL` or `API_KEY` is missing.

### Running Locally

```bash
# Set required env vars
export API_BASE_URL="https://api.example.com/v1"
export API_KEY="sk_live_abc123"
export ADDED_FILES="sources/source1.yaml"

# POST the document
python scripts/post_requests.py
```

## Workflows

### PR Validation (`validate.yml`)

| Trigger | Target branch | Paths |
|---------|---------------|-------|
| `pull_request` | `main` | `sources/**`, `claims/**`, `proofs/**` |

Runs on the PR source branch and validates all tracked files using `validate.py`.

### POST on Merge (`post_on_merge.yml`)

| Trigger | When it runs |
|---------|--------------|
| `push` to `main` | After PR merge |
| `workflow_dispatch` | Manual trigger from Actions tab |

For both triggers, the workflow:
1. Checks out the repo with full history (`fetch-depth: 0`).
2. Computes `git diff --diff-filter=A HEAD~1 HEAD --name-only` to find files **added in the latest commit**.
3. Passes those files to `post_requests.py` via the `ADDED_FILES` env var.
4. Only runs the POST step if at least one tracked file was added.

## Workflow Rules & Assumptions

- **PRs only add new files.** They never modify existing documents or the `oapi.yaml` schema.
- **New documents must be valid before merge.** The PR validation workflow blocks merge if validation fails.
- **Documents must live in the correct folder.** Files placed in the wrong folder are ignored by both scripts but may still trigger CI workflows.
- **Schema changes are rare and separate.** If `oapi.yaml` ever changes, all existing documents must be re-validated and updated in the same or an earlier PR.
- **POST workflow requires secrets.** `API_BASE_URL` and `API_KEY` must be configured in repository settings for the merge workflow to succeed.

## Instructions for AI Agents

### When generating a new document

1. Read `oapi.yaml` to identify the correct schema for the target folder.
2. Produce a document that satisfies **all** `required` fields and respects type constraints (`minimum`, `maximum`, `minLength`, `enum`, etc.).
3. Use YAML unless JSON is explicitly requested.
4. Save the file directly into the appropriate folder (e.g., `sources/`).
5. Run `python scripts/validate.py <file>` locally before suggesting the change.

### When reviewing a PR

1. Confirm the new file(s) are in the correct tracked folder.
2. Check that no existing files were modified (per repository policy).
3. If the PR changes `oapi.yaml`, flag it — schema changes must be handled separately.
4. Verify the document satisfies required fields and constraint bounds from the schema.
5. Suggest running `python scripts/validate.py` if validation results are not visible in CI.

### When modifying scripts or CI

- Keep `validate.py` dependency-free except for `pyyaml`, `jsonschema`, and `referencing`.
- `validate.py` should default to scanning all tracked files when called without arguments.
- `post_requests.py` must crash with a clear error if `API_BASE_URL` or `API_KEY` is unset.
- Never add `git diff` logic into the Python scripts; the CI checkout already provides the correct working tree.
- Maintain the folder-to-schema mapping in a single dictionary at the top of both scripts.
- Keep the `oapi.yaml` `paths` section in sync with the schema `$ref` mappings used by the scripts.

## Schema & API Reference

| Folder | Schema Name | POST Path | Key Constraints |
|--------|-------------|-----------|-----------------|
| `sources/` | `SourceInput` | `/api/v1/source` | `name`: required non-empty; `summary`: required non-empty; `tags`: required (comma-separated, no spaces); `uri`: required HTTPS URL |
| `claims/` | `ClaimInput` | `/api/v1/claim` | `sourceUriDigest`: required (SHA-256) non-empty; `title`: required non-empty; `summary`: required non-empty; `uri`: required HTTPS URL |
| `proofs/` | `ProofInput` | `/api/v1/proof` | `claimUriDigest`: required non-empty (no spaces); `reviewedBy`: required non-empty (no spaces); `uri`: required HTTPS URL; `supportsClaim`: required boolean |

The `oapi.yaml` `paths` section must contain a `post` operation for each schema with `requestBody.content.application/json.schema.$ref` pointing to the corresponding schema. The POST script uses this `$ref` to map schemas to their endpoint paths.

For full schema and API details, inspect `oapi.yaml` directly.