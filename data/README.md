# Data Directory

Local data, none of it committed to git.

## Three lifecycles, three prefixes

The top level answers one question by looking: **what is irreplaceable?**

| Prefix | Lifecycle | If you delete it |
| --- | --- | --- |
| `packs/` | Reinstallable | `pnpm run setup` clones it again |
| `runtime/` | Disposable | Regenerated on the next run, at the cost of time |
| `tenants/` | Irreplaceable | **Gone.** This is the only prefix a backup has to carry |

```text
data/
├── packs/mpmb/
│   ├── source_2014/          clone of MPMB's master repo
│   ├── source_2024/          clone of MPMB's 2024 repo
│   ├── imports/              clone of safety-orange's Imports repo
│   ├── adobe_docs/           Acrobat/AcroJS reference PDFs
│   ├── pdfs/                 MPMB-distributed PDFs
│   └── character_sheets/     sample filled sheets
├── runtime/
│   ├── chunked_output/       chunker JSON the indexer embeds into Qdrant
│   ├── index_cache/          cached embeddings, plus index_status.json
│   ├── extracted/            extracted document text, keyed by content hash
│   └── models/fastembed/     durable ONNX cache for the embedder and reranker
├── tenants/<tenant_id>/      uploads, per tenant - see "Storage keys" below
├── intent_examples.json      seed phrases the intent classifier builds centroids from
└── settings.json             hot-reloaded behavioral settings (PATCH /api/settings writes here)
```

The model cache lives under `runtime/` rather than the OS temp directory because a
Windows temp cleanup half-deletes an ONNX snapshot: fastembed then skips the download
and the runtime fails to load the missing file, which reads as broken retrieval.

## Storage keys

Everything under `tenants/` is addressed by a **storage key**, and the key is what the
`files` table stores:

```text
tenants/<tenant_id>/_meta.json
tenants/<tenant_id>/by-name.json                                  generated, tenant-scoped
tenants/<tenant_id>/library/<filename>                            the tenant's shared library
tenants/<tenant_id>/users/<user_id>/_meta.json
tenants/<tenant_id>/users/<user_id>/global/<filename>             one user's personal library
tenants/<tenant_id>/users/<user_id>/sessions/<session_id>/<filename>
```

Two rules make the scheme survive a move to an object store, and both are also good
filesystem hygiene:

- **No key segment is ever a name.** Every segment is a primary key, so renaming a
  tenant, a user or a chat moves no bytes. `by-name.json` exists precisely so the tree
  stays readable without putting names in keys - and it lives *inside* the tenant,
  because a single root-level index would expose every tenant's usernames to anyone who
  can list the bucket.
- **Prefix existence carries no meaning.** An empty prefix cannot exist in an object
  store, so nothing infers anything from a directory being present.

`_meta.json` is a breadcrumb, not a record. It is projected from the database after the
commit, never inside it, and it is safe to delete - `pnpm run storage:verify` reports
any that disagree with their row.

## Checking for drift

```bash
pnpm run storage:verify
```

Reports three kinds of drift and exits non-zero on any: objects on disk that no row
claims, rows that point at nothing on disk, and breadcrumbs that disagree with their
row. **It never repairs.** The correct repair differs per direction, and an orphaned
object may be the only copy of someone's upload.

## Setup

Bootstrapped from the repo root. The setup script is cross-platform Node - no PowerShell
required.

```bash
pnpm run setup
```

What the script does:

1. Creates `.env` from `.env.example` when missing, pointing Postgres/Qdrant at the host
2. Installs the backend Python dependencies with `uv sync --locked`
3. Reports the ONNX execution provider and, on a first run, opts into GPU inference
4. Clones or updates the three source repositories under `packs/mpmb/`
5. Runs the source analyzer, then the chunker, writing JSON into `runtime/chunked_output/`

Useful flags: `--skip-dependencies` reuses the existing `backend/.venv`; `--dry-run`
reports what would change without touching anything.

The setup script does not start Docker or run indexing. It is only responsible for
environment preparation, source acquisition, and chunk generation. `pnpm run setup:all`
chains it with `setup:services` (postgres + qdrant) and `setup:index`.

## Notes

- Placeholder files such as `.gitkeep` may exist so a directory structure can be committed. The setup script removes those placeholders when it needs to clone a repo into that folder.
- Source and output locations can be overridden through `.env` values such as `MPMB_SOURCE_DIR`, `MPMB_SOURCE_2024_DIR`, `IMPORTS_SOURCE_DIR`, and `CHUNKED_OUTPUT_DIR`.
- Source repository defaults can be overridden with `MPMB_REPO_URL`, `MPMB_REPO_2024_URL`, `MPMB_REPO_BRANCH_2014`, `MPMB_REPO_BRANCH_2024`, and `IMPORTS_REPO_URL`.
