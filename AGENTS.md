# AGENTS.md — Repository Guide for AI Assistants

## Repository Overview

This repository stores structured request documents organized by type. Each folder corresponds to a schema defined in `openapi.yaml`. All documents must conform to their folder's schema.

### Directory Layout

```text
.
├── openapi.yaml                    # Single source of truth for all schemas
├── grant_requests/                 # Grant application documents
├── admission_requests/             # Admission application documents
├── scripts/
│   └── validate.py                 # Validates documents against schemas
└── .github/workflows/
    └── validate.yml                # Runs validate.py on every PR
```

## What the Validation Script Does

`scripts/validate.py` performs the following:

1. Loads `openapi.yaml` and extracts schemas from `components.schemas`.
2. Maps folders to schema names:
   - `grant_requests/` → `GrantRequest`
   - `admission_requests/` → `AdmissionRequest`
3. Scans each tracked folder for `.yaml`, `.yml`, and `.json` files.
4. Validates every found document against its corresponding schema using JSON Schema Draft 2020-12.
5. Reports pass/fail per file with specific field-level errors.

### Running Locally

```bash
# Validate all documents in tracked folders
python scripts/validate.py

# Validate specific files only
python scripts/validate.py grant_requests/my-project.yaml
```

### Dependencies

```bash
pip install pyyaml jsonschema referencing
```

## Workflow Rules & Assumptions

- **New documents must be valid before merge.** The GitHub Action blocks merge if validation fails.
- **Documents must live in the correct folder.** Files placed in the wrong folder are ignored by the validator but may still trigger the CI workflow.
- **Schema changes are rare and separate.** If `openapi.yaml` ever changes, all existing documents must be re-validated and updated in the same or an earlier PR.

## Instructions for AI Agents

### When generating a new document

1. Read `openapi.yaml` to identify the correct schema for the target folder.
2. Produce a document that satisfies **all** `required` fields and respects type constraints (`minimum`, `maximum`, `minLength`, `enum`, etc.).
3. Use YAML unless JSON is explicitly requested.
4. Save the file directly into the appropriate folder (e.g., `grant_requests/`).
5. Run `python scripts/validate.py <file>` locally before suggesting the change.

### When reviewing a PR

1. Confirm the new file(s) are in the correct tracked folder.
2. Check that no existing files were modified (per repository policy).
3. If the PR changes `openapi.yaml`, flag it — schema changes must be handled separately.
4. Verify the document satisfies required fields and constraint bounds from the schema.
5. Suggest running `python scripts/validate.py` if validation results are not visible in CI.

### When modifying the script or CI

- Keep the script dependency-free except for `pyyaml`, `jsonschema`, and `referencing`.
- The script should default to scanning all tracked files when called without arguments.
- Never add `git diff` logic into the Python script; the CI checkout already provides the correct working tree.
- Maintain the folder-to-schema mapping in a single dictionary at the top of `validate.py`.

## Schema Reference

| Folder | Schema Name | Key Constraints |
|--------|-------------|-----------------|
| `grant_requests/` | `GrantRequest` | `applicant` ≥ 2 chars, `amount` ≥ 1000, `purpose` ≥ 20 chars, `timeline_months` 1–36 |
| `admission_requests/` | `AdmissionRequest` | `name` ≥ 2 chars, `program` ∈ {undergraduate, graduate, phd}, `gpa` 0.0–4.0, `statement` ≥ 50 chars |

For full schema details, inspect `openapi.yaml` directly.