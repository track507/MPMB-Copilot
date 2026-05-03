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

Users should run `npm run setup` or `scripts/setup.ps1` after unpacking to clone/update the external MPMB source repositories.

## CI/CD Workflows

- `.github/workflows/ci.yml`
  - lint, format check, tests, type checks
  - frontend production build artifact
  - Docker Compose validation
  - backend Docker image build
  - standalone analyzer compile smoke test

- `.github/workflows/security.yml`
  - dependency review on pull requests
  - CodeQL for Python and JavaScript/TypeScript
  - npm audit
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

## Current Action Majors

These were checked against primary GitHub project pages before adding the workflows:

- `actions/checkout@v6`
- `actions/setup-node@v6`
- `actions/setup-python@v6`
- `actions/upload-artifact@v7`
- `github/codeql-action/*@v4`
- `actions/dependency-review-action@v4`
- `astral-sh/setup-uv@v8.0.0`
- `aquasecurity/trivy-action@v0.35.0`
- `anchore/sbom-action@v0.24.0`
- `ossf/scorecard-action@v2.4.3`

Dependabot is configured to open weekly update PRs for GitHub Actions, npm, Python, and Docker dependencies.
