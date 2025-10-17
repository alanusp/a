# Contributing to AegisFlux

Thank you for improving AegisFlux! This document explains how to work within the repository while keeping reproducibility and air-gap guarantees intact.

## Development Environment

1. Install Python 3.11 and Node 20.
2. Clone the repository and install dependencies:
   ```bash
   python -m pip install -r requirements.lock
   npm ci --offline || true
   ```
3. Optional: `make dev` installs editable extras.

## Key Make Targets

| Command | Purpose |
| ------- | ------- |
| `make test` | Run the entire pytest suite. |
| `make typecheck` | Run MyPy in strict mode. |
| `make clients` | Regenerate Python/TS SDKs. |
| `make shots` | Capture screenshots (Docker or local fallback). |
| `make docs-verify` | Ensure docs include maintainer contacts and screenshots. |
| `make openapi-export` | Export the current OpenAPI spec to `artifacts/openapi/current.json`. |
| `make openapi-diff` | Classify OpenAPI SemVer impact. |
| `make repro-build` | Verify reproducible zipapp/image hashes. |

## Commit Style

- Follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.
- Maintain semantic versioning when releasing artifacts.
- Sign commits with the Developer Certificate of Origin:
  ```
  Signed-off-by: Your Name <your.email@example.com>
  ```

## Pull Requests

Before opening a PR, ensure the following checklist is green:

- [ ] `pytest -q`
- [ ] `make typecheck`
- [ ] `make lint`
- [ ] `make clients`
- [ ] `make shots`
- [ ] `make docs-verify`
- [ ] `make openapi-export && make openapi-diff`
- [ ] `make repro-build`
- [ ] `make verify-sigs`

Include notes about performance (latency, throughput), security (new secrets, network egress), and migration/rollout implications in the PR description.

## Code Review Expectations

- Tests must accompany behavioral changes.
- CI must remain air-gap friendly; no external downloads beyond the vendored wheelhouse/Playwright caches.
- Keep configuration changes deterministic and idempotent.

## Contact

Maintainer: **Alan Uriel Saavedra Pulido** <alanursapu@gmail.com>
