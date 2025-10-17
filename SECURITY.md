# Security Policy

## Supported Branches

| Branch | Supported | Notes |
| ------ | --------- | ----- |
| `main` | ✅        | Rolling releases with reproducible builds and SBOMs |
| others | ⚠️        | Best-effort support only; please rebase onto `main` |

## Reporting a Vulnerability

Please email **Alan Uriel Saavedra Pulido** at **alanursapu@gmail.com** with a detailed description, reproduction steps, and any logs or crash dumps you can provide. Include `[AegisFlux Security]` in the subject line.

We aim to acknowledge new reports within 2 business days and provide an initial assessment within 7 business days. If remediation requires coordinated disclosure, we will agree on a disclosure timeline with you.

```text
-----BEGIN PGP PUBLIC KEY BLOCK-----
# Reserved for future publication. Please request if needed.
-----END PGP PUBLIC KEY BLOCK-----
```

## Disclosure Process

1. **Triage** – We validate the issue, confirm severity, and reproduce the impact.
2. **Fix** – A patch is prepared, reviewed, and merged with all reproducibility gates green.
3. **Release** – Updated artifacts (SBOM, OpenAPI, clients) are produced and signed.
4. **Advisory** – A security notice is published with mitigation steps and credits.

We prefer coordinated disclosure and will request at least 14 days to prepare fixes before public disclosure unless exploitation is active.

## Dependency Security

- SBOM generated via `make sbom`; verified with `make verify-sigs`.
- Third-party packages pinned in `requirements.lock` and vendored via `airgap/` tooling.
- Playwright and browser binaries are cached inside the repo for air-gapped CI runs.

## Reproducibility Guarantees

- Every release provides reproducible container images (amd64 + arm64) verified by `make repro-multiarch`.
- OpenAPI and SDK diffs are SemVer-gated; reproducible bundles live under `artifacts/`.
- Integrity monitors (`make integrity`) ensure the running stack matches `artifacts/version_manifest.json`.
