# Docs Repository — Sources, Claims, Proofs

This repository stores structured request documents (organized into `sources/`, `claims/`, and `proofs/`), the OpenAPI schema that defines their expected shape, and helper scripts used by CI to validate and POST new documents to an API.

## Directory layout

- `oapi.yaml` — OpenAPI / schema file that defines the JSON schemas used for documents and the POST endpoints.
- `sources/` — Source documents (YAML files) that describe original sources.
- `claims/` — Claim documents (YAML files) that assert specific claims and reference sources.
- `proofs/` — Proof documents (YAML files) that support or refute claims.
- `scripts/` — Validation and POST helper scripts. See [scripts/validate.py](scripts/validate.py) and [scripts/post_requests.py](scripts/post_requests.py).
- `requirements.txt` — Python dependencies for running the scripts locally.
- `AGENTS.md` — guidance for AI agents working with this repo.

## Workflows

- PR Validation: A GitHub Actions workflow runs on pull requests (to `main`) and executes `python scripts/validate.py` to validate any new documents in the tracked folders. This ensures added documents conform to the schemas in `oapi.yaml` before merge.
- Post-on-merge: After a PR is merged to `main`, another workflow runs `python scripts/post_requests.py` and POSTs newly added files to configured API endpoints. The POST script expects `API_BASE_URL` and `API_KEY` environment variables and receives the list of added files via the `ADDED_FILES` environment variable.
- Verify Claims and Source Scores: A dedicated workflow (scheduled or on-demand) verifies claims in `claims/` and computes or updates source scores. The canonical verification and scoring logic is maintained in the `source-score` project (see note below).

See `scripts/validate.py` and `scripts/post_requests.py` for exact behavior and failure modes.

## Role of the OpenAPI schema (`oapi.yaml`)

- Single source of truth: `oapi.yaml` contains the document schemas (eg. `SourceInput`, `ClaimInput`, `ProofInput`) under `components.schemas` and maps those schemas to POST paths under `paths`.
- Validation: `scripts/validate.py` loads the relevant schema from `oapi.yaml` and validates new YAML docs against it (JSON Schema Draft 2020-12).
- Routing: `scripts/post_requests.py` maps schema `$ref`s to the API `paths` so that validated documents are posted to the correct endpoint.

- Important: `oapi.yaml` in this repository is a copy and should never be edited here. The source of truth for the schema is the `source-score` repository: https://github.com/SatyaLens/source-score.

## How to add new documents

1. Identify the correct folder and schema in `oapi.yaml` for your document type (`sources/`, `claims/`, or `proofs/`).
2. Create a new YAML file in the appropriate folder, satisfying all `required` fields from the schema. Example constraints are documented in `oapi.yaml` (and summarized in `AGENTS.md`).
3. Validate locally before opening a PR:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/validate.py path/to/your-file.yaml
```

4. Open a PR that only *adds* new files (per repo rules). The CI validation workflow will run automatically.
5. After merge, the post-merge workflow will run `scripts/post_requests.py` for any newly added tracked files and attempt to POST them to the configured API.

Notes about `post_requests.py`: it requires `API_BASE_URL` and `API_KEY` to be set in the environment (CI supplies these as a variable and secret respectively). Locally you can run the script with those env vars, but be careful with credentials.

## Important note — First iteration

**Important:** This directory layout and workflow are a first iteration to make document validation and posting work. The structure of `sources/`, `claims/`, and `proofs/` will most likely change in future updates to make it easier to author and contribute new documents. Expect schema refinements, directory reorganizations, and improved developer ergonomics in later iterations.