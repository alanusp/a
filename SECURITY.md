# Security Policy

## Supported Branches
- `main`: actively supported with security updates.
- Release tags: receive fixes while under active maintenance; older tags require upgrade to latest patch.

## Reporting a Vulnerability
Please email **Alan Uriel Saavedra Pulido** at **alanursapu@gmail.com** with a descriptive report and proof-of-concept if possible. We acknowledge reports within 72 hours and provide a remediation or mitigation plan within 7 calendar days.

> PGP: (coming soon) — we will publish a public key for encrypted reports in this section.

## Disclosure Process
1. We confirm the issue and develop a private fix or mitigation.
2. Coordinated disclosure is targeted within 30 days, or later by mutual agreement.
3. Credit is granted in release notes unless anonymity is requested.

## Dependency and Supply Chain Management
- SBOMs are generated via `make sbom` and signed artifacts are verified on boot.
- Third-party dependencies are pinned in `requirements.lock` and vendored wheelhouses for offline builds.
- Container images are reproducible and checked for drift with `make repro-build` and `make repro-multiarch`.

## Reproducible Builds
We require deterministic artefacts prior to release. `make repro` and the integrity monitor verify hashes for source, OpenAPI specs, and SDKs.

## Incident Response
For exploitable vulnerabilities, enable read-only degrade mode via `MAINTENANCE_FREEZE=1`, run `make drain-start`, and follow the generated incident runbook (`make runbook`).
