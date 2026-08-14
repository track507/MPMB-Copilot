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
- cloned MPMB source repos in `data/mpmb_source`, `data/mpmb_source_2024`, and `data/imports_source`
- generated chunks, indexes, uploads, logs, and analyzer reports

Users should run `pnpm run setup` after unpacking. It needs `git`, `uv`, and `pnpm` on `PATH`, and it creates `.env`, installs the backend Python dependencies with `uv sync --locked`, clones/updates the external MPMB source repositories, then runs the analyzer and the chunker.

## CI/CD Workflows

- `.github/workflows/ci.yml`
  - lint, format check, tests
  - optional non-blocking type checks when `ENABLE_TYPECHECK=true`
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
  - tests
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

Python mypy currently reports existing backend typing debt. CI therefore runs `pnpm run check` as the required quality gate, while `pnpm run check:full` remains available locally. Set `ENABLE_TYPECHECK=true` later after the backend typing debt is paid down.

The standalone analyzer smoke test only runs when `scripts/analyze/analyze-repos.py` and `scripts/analyze/src/mpmb_repo_analyzer/__main__.py` are present in the checked-out commit. This lets CI stay green before the analyzer tool is committed.

## Current Action Majors

These were checked against primary GitHub project pages before adding the workflows:

- `actions/checkout@v6`
- `actions/setup-node@v6`
- `actions/setup-python@v6`
- `actions/upload-artifact@v7`
- `github/codeql-action/*@v4`
- `actions/dependency-review-action@v5`
- `astral-sh/setup-uv@v8.2.0`
- `pnpm/action-setup@v6`
- `aquasecurity/trivy-action@v0.35.0`
- `anchore/sbom-action@v0.24.0`
- `ossf/scorecard-action@v2.4.3`

Dependabot is configured to open weekly update PRs for GitHub Actions, npm, Python, and Docker dependencies.
