# Release Process

MPMB-Copilot publishes downloadable GitHub Release bundles from CI/CD.

## Release Channels

- `main` publishes or updates the mutable `main-latest` release.
- `develop` publishes or updates the mutable `develop-latest` prerelease.
- Tags matching `v*` publish immutable version releases, for example `v0.1.0`.
- Tags containing a hyphen, such as `v0.2.0-beta.1`, are marked as prereleases.

## Release Assets

Each release uploads:

- `mpmb-copilot-<tag>.zip`
- `mpmb-copilot-<tag>.tar.gz`
- `mpmb-copilot-<tag>.SHA256SUMS.txt`
- `mpmb-copilot-<tag>.spdx.json`, when SBOM generation succeeds

The bundle includes application source, lock files, Docker configuration, setup scripts, docs, and a built `frontend/dist`.

The bundle intentionally excludes:

- `.env` secrets
- `node_modules`
- Python virtual environments
- everything under `data/packs/` (cloned MPMB sources and pack assets - `pnpm run setup` re-clones them)
- everything under `data/runtime/` (chunks, index cache, extracted text, the ONNX model cache)
- everything under `data/tenants/` (uploads, which are tenant data and must never ship in a bundle)
- logs and analyzer reports

Users should run `pnpm run setup` after unpacking. It needs `git`, `uv`, and `pnpm` on `PATH`, and it creates `.env`, installs the backend Python dependencies with `uv sync --locked`, clones/updates the external MPMB source repositories, then runs the analyzer and the chunker.

## CI/CD Workflows

- `.github/workflows/ci.yml`
  - `pnpm run check`: lint, import contracts, format check, typecheck (ty + tsc), pytest
  - a Postgres service, so the `tests/services/db` suite runs instead of skipping
  - frontend production build artifact
  - Docker Compose validation
  - backend Docker image build
  - standalone analyzer compile smoke test

- `.github/workflows/security.yml`
  - dependency review on pull requests
  - CodeQL for Python and JavaScript/TypeScript
  - pnpm audit
  - pip-audit
  - Trivy filesystem SARIF scan
  - OpenSSF Scorecard

- `.github/workflows/release.yml`
  - `pnpm run check`, the same gate as CI, against the same Postgres service
  - frontend build
  - Docker validation/build
  - self-contained bundle creation
  - SBOM generation
  - checksum generation
  - GitHub Release publishing

Security jobs are intentionally non-blocking because some GitHub native scanning features require public repositories or GitHub Advanced Security. Their reports are still uploaded as workflow artifacts when possible.

Code scanning upload is disabled by default to keep private/non-GHAS repositories green. To opt in later, enable code scanning in repository settings and add repository variables:

- `ENABLE_DEPENDENCY_REVIEW=true`
- `ENABLE_CODEQL=true`
- `ENABLE_CODE_SCANNING_UPLOAD=true`

Without those variables, the workflow still runs pnpm, Python, Trivy, and Scorecard-style checks where possible, but it does not call GitHub's Dependency Review or SARIF/code-scanning APIs.

Python typechecking (`ty`, which replaced mypy on 2026-09-19) reached zero diagnostics on 2026-09-20 and runs inside `pnpm run check`, the required quality gate - so both backend (`ty`) and frontend (`tsc`) typechecking gate every push and every CI run. The standalone `typecheck` job behind `vars.ENABLE_TYPECHECK` was removed on 2026-09-25: it was `continue-on-error`, so it could not fail, and `check` had been typechecking unconditionally for five days. `pnpm run check:full` remains a duplicate of `check` and runs typecheck twice.

Until 2026-09-25 the release job ran `pnpm run test` alone, so a release could be built and published while lint, format, typecheck or the import contracts were red. It now runs the whole gate. `pnpm run typecheck:scripts` is still outside every gate on purpose - the older ops scripts do not pass `tsc` with `checkJs`.

The standalone analyzer smoke test only runs when `scripts/analyze/analyze-repos.py` and `scripts/analyze/src/mpmb_repo_analyzer/__main__.py` are present in the checked-out commit. This lets CI stay green before the analyzer tool is committed.

## Current Action Majors

These were checked against primary GitHub project pages before adding the workflows:

- `actions/checkout@v6`
- `actions/setup-node@v6`
- `actions/setup-python@v6`
- `actions/upload-artifact@v7`
- `github/codeql-action/*@v4`
- `actions/dependency-review-action@v5`
- `astral-sh/setup-uv@v10.1.0`
- `pnpm/action-setup@v6`
- `aquasecurity/trivy-action@v0.36.0`
- `anchore/sbom-action@v0.24.2`
- `ossf/scorecard-action@v2.4.4`

Every `uses:` is pinned to a commit SHA with the version in a trailing comment, so this list is a summary and the workflow files are the truth.

Dependabot opens weekly update PRs for GitHub Actions, npm, Python, and Docker dependencies, each with a three-day cooldown. That cooldown must stay above `minimumReleaseAge` in `pnpm-workspace.yaml` (1440 minutes), or Dependabot opens npm PRs whose `pnpm install` is refused and which are red before anyone reads them.
