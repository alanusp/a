SHELL := /bin/bash
.PHONY: dev up down logs seed test itest e2e k6 chaos schemathesis mutate replay sbom scan sign release doctor profile lock airgap airgap-load tla opa-test zipapp probe dr-backup dr-restore explain-smoke perf-baseline perf-compare audit-verify secret-scan license-gate sketch-bench ppr-bench forecast hdr-baseline hdr-compare flags-check golden golden-approve hygiene config-lint caps-check clients burn-gate health repro forbidden dual-write-start dual-write-backfill dual-write-validate dual-write-cutover dual-write-rollback dual-write-status drain-start drain-stop drain-status crashloop-test wal-rotate avro-canonical git-hygiene deprecation-gate units-check env-check slo-gate yaml-gate case-gate perms-check receipts typecheck repro-build flake-detect verify-sigs reload rename shots lfs-init docs-verify lint-docs
				
dev:
	python -m pip install --upgrade pip
	python -m pip install -e .[dev]

up:
	docker-compose up -d

down:
	docker-compose down --remove-orphans

logs:
	docker-compose logs --tail=100

seed:
	python scripts/seed_kafka.py

test:
	pytest

itest:
	pytest tests/test_streaming_utils.py tests/test_contracts.py

e2e:
	pytest tests/test_inference.py tests/test_replay.py

k6:
	python scripts/run_k6_gate.py

chaos:
	pytest tests/test_chaos_resilience.py

schemathesis:
	pytest tests/test_contracts.py

mutate:
	python scripts/run_mutation_score.py

replay:
	pytest tests/test_replay.py

sbom:
	python scripts/generate_sbom.py

scan:
	python scripts/security_scan.py

sign:
	python scripts/sign_artifacts.py

release:
	python scripts/prepare_release.py

doctor:
	python scripts/doctor.py

profile:
	python scripts/profile_e2e.py

lock:
	python -m pip freeze > requirements.lock

airgap:
	python airgap/build_wheelhouse.py

airgap-load:
	bash airgap/load_images.sh

tla:
	bash scripts/run_tla.sh

opa-test:
	python scripts/opa_eval.py

zipapp:
	python scripts/zipapp_build.py

probe:
	python scripts/synthetic_probe.py

rename:
	@test -n "$(NAME)" || (echo "NAME is required" && exit 1); MODULE="$(MODULE)"; if [ -z "$$MODULE" ]; then MODULE=$$(printf "%s" "$(NAME)" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]' '-' | sed 's/^-//;s/-$$//'); fi; python scripts/rename_project.py --name "$(NAME)" --module "$$MODULE"

shots:
	@set -euo pipefail; \
	if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		echo "[shots] using docker compose"; \
		docker compose up -d api >/dev/null 2>&1 || true; \
		docker compose run --rm shots python /app/scripts/capture_screens.py --base http://api:8000 --out /app/docs/assets; \
		docker compose stop api >/dev/null 2>&1 || true; \
	else \
		echo "[shots] docker unavailable, using local uvicorn"; \
		if command -v uvicorn >/dev/null 2>&1; then \
			need_boot=$$(curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1 || echo 1); \
			if [ -n "$$need_boot" ]; then \
				uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning & \
				server_pid=$$!; \
				trap "kill $$server_pid >/dev/null 2>&1 || true" EXIT; \
				python scripts/capture_screens.py --base http://127.0.0.1:8000 --out docs/assets; \
				kill $$server_pid >/dev/null 2>&1 || true; \
				wait $$server_pid 2>/dev/null || true; \
			else \
				python scripts/capture_screens.py --base http://127.0.0.1:8000 --out docs/assets; \
			fi; \
		else \
			python scripts/capture_screens.py --base http://127.0.0.1:8000 --out docs/assets; \
		fi; \
	fi

lfs-init:
	git lfs install
	git lfs track "docs/assets/*" "*.png" "*.jpg" "*.jpeg" "*.webp" "*.avif"
	git add .gitattributes
	@echo "Tracked image assets with Git LFS. Run 'git add -f docs/assets/*' to stage existing binaries."
	@echo "When collaborating, remind contributors to run 'make lfs-init' once per clone."
docs-verify:
	python scripts/docs_verify.py

lint-docs:
	python scripts/docs_verify.py --strict

dr-backup:
	python scripts/backup_redis.py
	python scripts/backup_redpanda.py

dr-restore:
	python scripts/restore_redis.py
	python scripts/restore_redpanda.py


explain-smoke:
	pytest tests/test_explainability.py

perf-baseline:
	python - <<'PY'
	from pathlib import Path
	import json
	path = Path('artifacts/perf')
	path.mkdir(parents=True, exist_ok=True)
	baseline = path / 'baseline.json'
	if not baseline.exists():
		baseline.write_text(json.dumps({'latencies': [40.0, 45.0, 50.0, 42.0, 48.0]}), encoding='utf-8')
	PY

perf-compare:
	python scripts/perf_compare.py

audit-verify:
	pytest tests/test_audit.py

secret-scan:
	python scripts/secret_scan.py

license-gate:
	python scripts/license_gate.py

sketch-bench:
	pytest tests/test_sketches.py

ppr-bench:
	pytest tests/test_graph_analytics.py

forecast:
	python scripts/forecast_retrain.py

hdr-baseline:
	python - <<'PY'
	from pathlib import Path
	from app.services.hdr import LatencyHistogram
	path = Path('artifacts/perf')
	path.mkdir(parents=True, exist_ok=True)
	hist = LatencyHistogram()
	for sample in (40, 42, 45, 47, 50):
	    hist.record(sample)
	(path / 'baseline.json').write_text(hist.to_json(), encoding='utf-8')
	PY

hdr-compare:
	python scripts/hdr_compare.py

flags-check:
	python scripts/flags_gate.py --schema-diff artifacts/schema_diff.json --required-flag new_schema

golden:
	python scripts/golden_check.py

golden-approve:
	python scripts/golden_check.py --approve

hygiene:
	python scripts/import_hygiene.py

config-lint:
	python scripts/config_lint.py

caps-check:
	python scripts/caps_check.py

units-check:
	pytest tests/test_inference.py::test_inference_probability_bounds -q

env-check:
	python -c "from app.core.env_invariants import enforce_environment_invariants; snap = enforce_environment_invariants(); print(f'env snapshot: {snap}')"

slo-gate:
	python scripts/slo_ci_gate.py

yaml-gate:
	python scripts/yaml_safety_gate.py

case-gate:
	python scripts/case_collision_gate.py

perms-check:
	python -c "from app.core.fs_perms import enforce_filesystem_permissions; enforce_filesystem_permissions(); print('filesystem permissions verified')"

receipts:
	python -c "from datetime import datetime; from app.core.receipts import issue_decision_receipt; payload={'event_id': 'test', 'tenant_id': 'tenant', 'probability': 0.5, 'decision': 'deny', 'timestamp': datetime.utcnow().isoformat()}; receipt = issue_decision_receipt(payload); print(f'issued receipt {receipt.identifier} -> {receipt.signature}')"

drain-start:
	python -c "from app.core.drain import get_drain_manager; print(get_drain_manager().start('manual'))"

drain-stop:
	python -c "from app.core.drain import get_drain_manager; print(get_drain_manager().stop())"

drain-status:
	python -c "from app.core.drain import get_drain_manager; print(get_drain_manager().status())"

crashloop-test:
	python -c "from app.core.crashloop import get_crashloop_breaker; b=get_crashloop_breaker(); b.record_boot(); b.record_boot(); b.record_boot(); print(b.state()); b.acknowledge()"

wal-rotate:
	python -c "from app.core.wal_rotate import get_wal_rotator; r=get_wal_rotator(); r.prune_oldest(); print({'manifest': getattr(r, '_manifest', {})})"

openapi-export:
	python scripts/openapi_export.py

openapi-diff:
	python scripts/openapi_diff.py

diag:
	python scripts/diag_bundle.py

drift-check:
	python scripts/drift_check.py --json

skew-gate:
	python scripts/version_skew_gate.py

parity:
	pytest tests/test_feature_parity.py

leak:
	python scripts/mem_leak_sentinel.py

bom:
	python scripts/bom_closure.py

examples:
	python scripts/openapi_examples_check.py

clients: openapi-export
	python scripts/gen_clients.py

burn-gate:
	python scripts/burn_rate_gate.py

health:
	python scripts/compose_health.py

repro:
	python scripts/repro_bundle.py

forbidden:
	python scripts/forbidden_api_gate.py

avro-canonical:
	python scripts/avro_canonical_gate.py

git-hygiene:
	python scripts/git_hygiene_gate.py

deprecation-gate:
	python scripts/deprecation_gate.py

redaction-gate:
	python scripts/redaction_gate.py

rollback-rehearsal:
	python scripts/rollback_rehearsal.py

integrity:
	python - <<'PY'
	from app.core.self_integrity import get_integrity_monitor

	monitor = get_integrity_monitor()
	ok = monitor.verify_once()
	print({"ok": ok, "status": monitor.status()})
	if not ok:
	raise SystemExit(1)
	PY

typecheck:
	mkdir -p artifacts/mypy
	python -m mypy --config-file mypy.ini \
	        app/core/reload.py app/core/admin_guard.py \
	        scripts/repro_image.py scripts/flake_detector.py scripts/verify_signatures.py \
	        --txt-report artifacts/mypy

repro-build:
	python scripts/repro_image.py

flake-detect:
	python scripts/flake_detector.py

verify-sigs:
	python scripts/verify_signatures.py

reload:
	python -m app.core.reload

disk-test:
	python scripts/disk_fill_tester.py --threshold 0.95

postmortem:
	python scripts/postmortem_bundle.py

shadow-readers:
	python - <<'PY'
	from app.services.shadow_reader import get_shadow_reader

	report = get_shadow_reader().report()
	print(report)
	PY

dual-write-start:
	python scripts/dual_write_cutover.py start

dual-write-backfill:
	python scripts/dual_write_backfill.py

dual-write-validate:
	python scripts/dual_write_cutover.py validate

dual-write-cutover:
	python scripts/dual_write_cutover.py commit

dual-write-rollback:
	python scripts/dual_write_cutover.py rollback

dual-write-status:
	python - <<'PY'
	from pprint import pprint
	from app.services.migration import get_migration_service

	pprint(get_migration_service().status())
	PY
	python scripts/repo_bloat_gate.py
