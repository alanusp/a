from __future__ import annotations

import json
import os
from hashlib import sha256
from functools import lru_cache
from pathlib import Path
from typing import List


class Settings:
    """Application configuration sourced from environment variables."""

    def __init__(self) -> None:
        self.project_name: str = os.getenv("PROJECT_NAME", "Hyperion Fraud Defense")
        self.api_v1_prefix: str = os.getenv("API_V1_PREFIX", "/v1")
        self.kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.kafka_topic: str = os.getenv("KAFKA_TOPIC", "transactions")
        self.redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.allowed_hosts: list[str] = self._parse_list(
            os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1")
        )
        self.egress_guard_enabled: bool = os.getenv("EGRESS_GUARD_ENABLED", "1").lower() in {
            "1",
            "true",
            "yes",
        }
        self.egress_allowlist: dict[str, set[str]] = self._parse_allowlist(
            os.getenv("EGRESS_ALLOWLIST", "")
        )
        self.feast_repo_path: Path = Path(os.getenv("FEAST_REPO_PATH", "feature_repo"))
        self.model_path: Path = Path(os.getenv("MODEL_PATH", "artifacts/model_state_dict.json"))
        self.model_candidate_path: Path = Path(
            os.getenv("MODEL_CANDIDATE_PATH", "artifacts/model_state_candidate.json")
        )
        self.calibration_path: Path = Path(
            os.getenv("CALIBRATION_BASELINE_PATH", "artifacts/calibration.json")
        )
        self.calibration_candidate_path: Path = Path(
            os.getenv("CALIBRATION_CANDIDATE_PATH", "artifacts/calibration_candidate.json")
        )
        self.model_input_dim: int = int(os.getenv("MODEL_INPUT_DIM", "22"))
        self.model_hidden_dims: List[int] = self._parse_int_list(
            os.getenv("MODEL_HIDDEN_DIMS", "64,32,16")
        )
        self.inference_threshold: float = float(os.getenv("INFERENCE_THRESHOLD", "0.5"))
        self.model_drift_threshold: float = float(os.getenv("MODEL_DRIFT_THRESHOLD", "0.98"))
        self.target_coverage: float = float(os.getenv("TARGET_COVERAGE", "0.9"))
        self.online_learning_rate: float = float(os.getenv("ONLINE_LEARNING_RATE", "0.05"))
        self.online_l2: float = float(os.getenv("ONLINE_L2", "0.0"))
        self.online_lr_decay: float = float(os.getenv("ONLINE_LR_DECAY", "0.0"))
        self.online_min_learning_rate: float = float(os.getenv("ONLINE_MIN_LR", "1e-4"))
        self.online_snapshot_interval: int | None = self._optional_int(
            os.getenv("ONLINE_SNAPSHOT_INTERVAL", "1000")
        )
        self.online_drift_threshold: float | None = self._optional_float(
            os.getenv("ONLINE_DRIFT_THRESHOLD", "0.25")
        )
        self.online_drift_patience: int = int(os.getenv("ONLINE_DRIFT_PATIENCE", "3"))
        self.calibrator_learning_rate: float | None = self._optional_float(
            os.getenv("CALIBRATOR_LEARNING_RATE", "0.01")
        )
        self.calibrator_l2: float = float(os.getenv("CALIBRATOR_L2", "0.0"))
        self.latency_budget_ms: int = int(os.getenv("LATENCY_BUDGET_MS", "200"))
        self.cold_start_budget_ms: int = int(os.getenv("COLD_START_BUDGET_MS", "3000"))
        self.singleflight_ttl_seconds: float = float(
            os.getenv("SINGLEFLIGHT_TTL_SECONDS", "5.0")
        )
        self.fanout_deadline_seconds: float = float(
            os.getenv("FANOUT_DEADLINE_SECONDS", "0.5")
        )
        self.enable_latency_alerts: bool = os.getenv("ENABLE_LATENCY_ALERTS", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        self.offline_dataset_path: Path = Path(
            os.getenv("OFFLINE_DATASET_PATH", "data/sample_transactions.csv")
        )
        self.feedback_store_path: Path = Path(
            os.getenv("FEEDBACK_STORE_PATH", "artifacts/feedback_store.jsonl")
        )
        self.privacy_salt_path: Path = Path(
            os.getenv("PRIVACY_SALT_PATH", "artifacts/privacy_salt.key")
        )
        self.dsar_dir: Path = Path(os.getenv("DSAR_DIRECTORY", "artifacts/dsar"))
        self.consent_state_path: Path = Path(os.getenv("CONSENT_STATE_PATH", "artifacts/consent.txt"))
        self.retention_days: int = int(os.getenv("RETENTION_DAYS", "30"))
        self.cost_false_positive: float = float(os.getenv("COST_FALSE_POSITIVE", "5.0"))
        self.cost_false_negative: float = float(os.getenv("COST_FALSE_NEGATIVE", "100.0"))
        self.cost_true_positive: float = float(os.getenv("COST_TRUE_POSITIVE", "-80.0"))
        self.cost_true_negative: float = float(os.getenv("COST_TRUE_NEGATIVE", "0.0"))
        self.policy_rules_path: Path = Path(os.getenv("POLICY_RULES_PATH", "rules"))
        self.conformal_window: int = int(os.getenv("CONFORMAL_WINDOW", "512"))
        self.fairness_window: int = int(os.getenv("FAIRNESS_WINDOW", "512"))
        self.console_static_path: Path = Path(os.getenv("CONSOLE_STATIC_PATH", "console"))
        self.dp_total_epsilon: float = float(os.getenv("DP_TOTAL_EPSILON", "5.0"))
        self.dp_metrics_epsilon: float = float(os.getenv("DP_METRICS_EPSILON", "0.5"))
        self.dp_seed: int = int(os.getenv("DP_SEED", "1337"))
        self.tenant_api_keys = self._parse_mapping(os.getenv("TENANT_API_KEYS", ""))
        self.enable_mtls: bool = os.getenv("ENABLE_MTLS", "false").lower() in {"1", "true", "yes"}
        self.mtls_artifact_dir: Path = Path(
            os.getenv("MTLS_ARTIFACT_DIR", "artifacts/mtls")
        )
        self.pki_directory: Path = Path(os.getenv("PKI_DIRECTORY", "artifacts/pki"))
        self.wheelhouse_path: Path = Path(os.getenv("WHEELHOUSE_PATH", "vendor/wheels"))
        self.audit_ledger_path: Path = Path(
            os.getenv("AUDIT_LEDGER_PATH", "artifacts/audit_ledger.jsonl")
        )
        self.audit_anchor_path: Path = Path(
            os.getenv("AUDIT_ANCHOR_PATH", "artifacts/ledger_anchor.txt")
        )
        self.key_manifest_path: Path = Path(
            os.getenv("KEY_MANIFEST_PATH", "artifacts/key_manifest.json")
        )
        self.base_wal_path: Path = Path(
            os.getenv("WAL_DIRECTORY", "artifacts/wal")
        )
        self.api_baseline_hash: str = os.getenv(
            "API_BASELINE_HASH",
            self._load_baseline_hash(),
        )
        self.max_model_age_seconds: int = int(os.getenv("MAX_MODEL_AGE_SECONDS", "86400"))
        self.maintenance_windows: str = os.getenv("MAINTENANCE_WINDOWS", "")
        self.online_updates_enabled: bool = os.getenv("ONLINE_UPDATES_ENABLED", "1").lower() in {
            "1",
            "true",
            "yes",
        }
        self.lineage_directory: Path = Path(
            os.getenv("LINEAGE_DIRECTORY", "artifacts/lineage")
        )
        self.perf_baseline_path: Path = Path(
            os.getenv("PERF_BASELINE_PATH", "artifacts/perf/baseline.json")
        )
        self.perf_report_path: Path = Path(
            os.getenv("PERF_REPORT_PATH", "artifacts/perf/report.md")
        )
        self.max_request_body: int = int(os.getenv("MAX_REQUEST_BODY", "131072"))
        self.read_timeout_seconds: float = float(os.getenv("READ_TIMEOUT_SECONDS", "5.0"))
        self.enable_waf: bool = os.getenv("ENABLE_WAF", "1").lower() in {"1", "true", "yes"}
        self.csp_policy: str = os.getenv(
            "CONTENT_SECURITY_POLICY",
            "default-src 'self'; frame-ancestors 'none'; script-src 'self'",
        )
        self.quota_default_qps: float = float(os.getenv("QUOTA_DEFAULT_QPS", "10.0"))
        self.quota_burst: float = float(os.getenv("QUOTA_BURST", "5.0"))
        self.redis_stream_soft_cap: int = int(os.getenv("REDIS_STREAM_SOFT_CAP", "2000"))
        self.redis_stream_hard_cap: int = int(os.getenv("REDIS_STREAM_HARD_CAP", "2500"))
        self.graph_node_soft_cap: int = int(os.getenv("GRAPH_NODE_SOFT_CAP", "50000"))
        self.graph_node_hard_cap: int = int(os.getenv("GRAPH_NODE_HARD_CAP", "75000"))
        self.graph_edge_soft_cap: int = int(os.getenv("GRAPH_EDGE_SOFT_CAP", "100000"))
        self.graph_edge_hard_cap: int = int(os.getenv("GRAPH_EDGE_HARD_CAP", "150000"))
        self.sketch_cardinality_soft_cap: int = int(
            os.getenv("SKETCH_CARDINALITY_SOFT_CAP", "200000")
        )
        self.sketch_cardinality_hard_cap: int = int(
            os.getenv("SKETCH_CARDINALITY_HARD_CAP", "250000")
        )
        self.graph_cache_ttl_seconds: float = float(
            os.getenv("GRAPH_CACHE_TTL_SECONDS", "5.0")
        )
        self.graph_cache_max_entries: int = int(
            os.getenv("GRAPH_CACHE_MAX_ENTRIES", "2048")
        )
        self.graph_negative_ttl_seconds: float = float(
            os.getenv("GRAPH_NEGATIVE_TTL_SECONDS", "2.0")
        )
        self.shutdown_flush_timeout: float = float(os.getenv("SHUTDOWN_FLUSH_TIMEOUT", "5.0"))
        self.candidate_traffic_percent: float = float(
            os.getenv("CANDIDATE_TRAFFIC_PERCENT", "0.0")
        )
        self.drain_accept_seconds: float = float(os.getenv("DRAIN_ACCEPT_SECONDS", "3.0"))
        self.drain_throttle_seconds: float = float(os.getenv("DRAIN_THROTTLE_SECONDS", "7.0"))
        self.crashloop_window_seconds: float = float(os.getenv("CRASHLOOP_WINDOW_SECONDS", "300"))
        self.crashloop_max_restarts: int = int(os.getenv("CRASHLOOP_MAX_RESTARTS", "3"))
        self.crashloop_state_path: Path = Path(
            os.getenv("CRASHLOOP_STATE_PATH", "artifacts/runtime/crashloop.json")
        )
        self.wal_rotate_max_bytes: int = int(os.getenv("WAL_ROTATE_MAX_BYTES", "5000000"))
        self.wal_rotate_max_age_seconds: float = float(
            os.getenv("WAL_ROTATE_MAX_AGE_SECONDS", "3600")
        )
        self.wal_rotate_max_archives: int = int(
            os.getenv("WAL_ROTATE_MAX_ARCHIVES", "8")
        )
        self.scored_topic_version: int = int(os.getenv("SCORED_TOPIC_VERSION", "1"))
        self.scored_topic_next_version: int = int(
            os.getenv("SCORED_TOPIC_NEXT_VERSION", str(self.scored_topic_version + 1))
        )
        self.dual_write_enabled: bool = os.getenv("DUAL_WRITE_ENABLED", "0").lower() in {
            "1",
            "true",
            "yes",
        }
        self.dual_write_parity_threshold: float = float(
            os.getenv("DUAL_WRITE_PARITY_THRESHOLD", "0.995")
        )
        self.dual_write_parity_window: int = int(
            os.getenv("DUAL_WRITE_PARITY_WINDOW", "512")
        )
        self.migration_state_path: Path = Path(
            os.getenv("MIGRATION_STATE_PATH", "artifacts/migration_state.json")
        )
        self.leader_ttl_seconds: float = float(os.getenv("LEADER_TTL_SECONDS", "10.0"))
        self.api_deprecations: dict[str, str] = self._parse_deprecations(
            os.getenv("API_DEPRECATIONS", "")
        )
        self.rlimit_nofile: int = int(os.getenv("RLIMIT_NOFILE", "1024"))
        self.rlimit_nproc: int = int(os.getenv("RLIMIT_NPROC", "512"))
        self.rlimit_as: int = int(os.getenv("RLIMIT_AS", str(512 * 1024 * 1024)))

    @staticmethod
    def _parse_int_list(raw: str) -> List[int]:
        values = [value.strip() for value in raw.split(",") if value.strip()]
        return [int(value) for value in values]

    @staticmethod
    def _optional_float(raw: str | None) -> float | None:
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    @staticmethod
    def _optional_int(raw: str | None) -> int | None:
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    @staticmethod
    def _parse_mapping(raw: str) -> dict[str, str]:
        mapping: dict[str, str] = {}
        if not raw:
            return mapping
        for pair in raw.split(";"):
            if not pair.strip():
                continue
            if ":" not in pair:
                continue
            api_key, tenant = pair.split(":", 1)
            mapping[api_key.strip()] = tenant.strip()
        return mapping

    @staticmethod
    def _parse_allowlist(raw: str) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        if not raw:
            return result
        for chunk in raw.split(";"):
            if not chunk.strip() or ":" not in chunk:
                continue
            host, tenants = chunk.split(":", 1)
            tenant_set = {tenant.strip().lower() or "*" for tenant in tenants.split(",") if tenant.strip()}
            result[host.strip().lower()] = tenant_set or {"*"}
        return result

    @staticmethod
    def _parse_list(raw: str) -> list[str]:
        return [item.strip() for item in raw.split(",") if item.strip()]

    @staticmethod
    def _parse_deprecations(raw: str) -> dict[str, str]:
        pairs: dict[str, str] = {}
        if not raw:
            return pairs
        for chunk in raw.split(";"):
            if not chunk.strip():
                continue
            if "|" not in chunk:
                continue
            path, sunset = chunk.split("|", 1)
            pairs[path.strip()] = sunset.strip()
        return pairs

    @staticmethod
    def _load_baseline_hash() -> str:
        manifest_path = Path("artifacts/version_manifest.json")
        if not manifest_path.exists():
            return "dev"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return "dev"
        openapi_meta = payload.get("openapi")
        if isinstance(openapi_meta, dict) and "sha256" in openapi_meta:
            return str(openapi_meta["sha256"])
        path = Path("artifacts/openapi/baseline.json")
        if path.exists():
            digest = sha256(path.read_bytes()).hexdigest()
            return digest
        return "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
