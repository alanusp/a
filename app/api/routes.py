from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any, Dict, Iterable

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.core.audit import MerkleLedger, get_ledger
from app.core.cache import get_cache_registry
from app.core.config import get_settings
from app.core.dp import DifferentialPrivacyAccountant, laplace_mechanism
from app.core.guardrails import SafetySwitch, get_safety_switch
from app.core.drain import get_drain_manager
from app.core.crashloop import get_crashloop_breaker
from app.core.ingest_signing import IngestSigner, IngestSignatureError
from app.core.diagnostics import build_bundle
from app.core.shutdown import get_shutdown_coordinator
from app.core.tenancy import TenantResolver
from app.core.trace import event_identifier, propagate_headers, start_trace
from app.core.startup import get_startup_state
from app.core.freeze import enforce_writable
from app.core.leadership import LeadershipError
from app.core.concurrency import TaskSpec, run_tasks
from app.core.receipts import issue_decision_receipt
from app.core.units import quantize_prob
from app.core.admin_guard import get_admin_guard
from app.services.console import ConsoleService
from app.services.contracts import HttpContractValidator
from app.services.decision import DecisionService
from app.services.feature_service import FeatureService
from app.services.feedback import FeedbackService
from app.services.dsar_ops import DSAROperator
from app.services.graph_features import GraphFeatureService, get_graph_feature_service
from app.services.inference_service import InferenceService
from app.services.lineage import LineageEmitter, get_lineage_emitter
from app.services.privacy import PrivacyService
from app.services.redis_stream import RedisStream
from app.services.shadow import ShadowTrafficService
from app.services.idempotency import get_idempotency_store
from app.services.traffic_router import TrafficRouter, get_traffic_router
from app.core.unicode_norm import canonical_email, canonical_phone, has_homoglyphs, normalize_identifier
from app.core.json_strict import parse_money
from app.services.migration import MigrationPhase, MigrationService, get_migration_service
from app.services.sla import get_sla_scheduler
from app.core.quotas import get_quota_manager
from quality.expectations import DEFAULT_EXPECTATIONS

try:
    from scripts.doctor import run_checks as doctor_checks
except ModuleNotFoundError:  # pragma: no cover - fallback for packaged install
    doctor_checks = lambda: {"status": "unknown"}


class TransactionPayload(BaseModel):
    transaction_id: str = Field(..., description="Unique transaction identifier")
    customer_id: str = Field(..., description="Customer identifier")
    merchant_id: str = Field(..., description="Merchant identifier")
    device_id: str = Field(..., description="Device fingerprint identifier")
    card_id: str = Field(..., description="Primary account number surrogate")
    ip_address: str = Field(..., description="Remote IP address")
    amount: Decimal
    currency: str
    device_trust_score: float = Field(ge=0.0, le=1.0)
    merchant_risk_score: float = Field(ge=0.0, le=1.0)
    velocity_1m: float = Field(ge=0.0)
    velocity_1h: float = Field(ge=0.0)
    chargeback_rate: float = Field(ge=0.0, le=1.0)
    account_age_days: float = Field(ge=0.0)
    customer_tenure: float = Field(ge=0.0)
    geo_distance: float = Field(ge=0.0)
    segment: str | None = Field(default=None, description="Optional fairness group tag")

    @model_validator(mode="before")
    @classmethod
    def _normalise_inputs(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        for field in [
            "transaction_id",
            "customer_id",
            "merchant_id",
            "device_id",
            "card_id",
            "ip_address",
        ]:
            raw = values.get(field)
            if isinstance(raw, str):
                values[field] = normalize_identifier(raw)
                if field in {"customer_id", "merchant_id", "device_id"} and has_homoglyphs(raw):
                    raise ValueError(f"{field} contains homoglyph characters")
        email = values.get("customer_email")
        if isinstance(email, str):
            values["customer_email"] = canonical_email(email)
        phone = values.get("customer_phone")
        if isinstance(phone, str):
            values["customer_phone"] = canonical_phone(phone)
        amount = values.get("amount")
        if amount is not None:
            if isinstance(amount, Decimal):
                values["amount"] = parse_money(str(amount))
            else:
                values["amount"] = parse_money(str(amount))
        return values


class PredictionResponse(BaseModel):
    transaction_id: str
    event_id: str
    tenant_id: str
    fraud_probability: float
    prediction_set: list[int]
    decision: str
    expected_cost: float
    threshold: float
    latency_ms: float
    metrics: Dict[str, float]
    reasons: list[str]
    receipt_id: str | None = None


class FeedbackPayload(BaseModel):
    event_id: str
    label: float
    observed_at: datetime
    group: str | None = None
    tenant_id: str | None = None


class FeedbackResponse(BaseModel):
    event_id: str
    tenant_id: str
    applied: bool
    updated: bool
    delay_seconds: float
    sample_weight: float


class DecisionPayload(TransactionPayload):
    strategy: str = Field(default="consensus")


class DecisionResponse(BaseModel):
    transaction_id: str
    tenant_id: str
    action: str
    expected_cost: float
    reasons: list[str]
    probability: float
    prediction_set: list[int]
    threshold: float


class ExplainPayload(TransactionPayload):
    event_id: str | None = None


class ExplainResponse(BaseModel):
    event_id: str | None
    bias: float
    probability: float
    contributions: Dict[str, float]
    counterfactual: dict[str, object]


class AuditProofResponse(BaseModel):
    event_id: str
    root: str
    proof: list[dict[str, str]]
    anchor: str


class DrainCommand(BaseModel):
    reason: str | None = Field(default=None, max_length=128)


class DrainStatusResponse(BaseModel):
    state: str
    phase: str
    reason: str | None
    seconds_since: float


class RuntimeAckResponse(BaseModel):
    tripped: bool
    reason: str | None


class DsarPayload(BaseModel):
    subject_id: str
    tenant_id: str | None = None


class DsarResponse(BaseModel):
    subject_id: str
    tenant_id: str
    records: list[dict[str, object]]


class ConsentPayload(BaseModel):
    version: str


class ConsentResponse(BaseModel):
    version: str


class CacheSummaryResponse(BaseModel):
    caches: Dict[str, Dict[str, float | int]]


class DiagResponse(BaseModel):
    path: str


class MigrationStatus(BaseModel):
    phase: str
    leader_actor: str | None
    parity: Dict[str, Any]
    rollback_count: int
    freeze: bool


class MigrationCommand(BaseModel):
    actor_id: str
    action: str = Field(
        default="commit",
        description="Migration action",
        regex="^(start|backfill|validate|commit|finalize)$",
    )

router = APIRouter()

REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "transaction_id": {"type": "string"},
        "customer_id": {"type": "string"},
        "merchant_id": {"type": "string"},
        "device_id": {"type": "string"},
        "card_id": {"type": "string"},
        "ip_address": {"type": "string"},
        "amount": {"type": "number"},
        "currency": {"type": "string"},
        "device_trust_score": {"type": "number"},
        "merchant_risk_score": {"type": "number"},
        "velocity_1m": {"type": "number"},
        "velocity_1h": {"type": "number"},
        "chargeback_rate": {"type": "number"},
        "account_age_days": {"type": "number"},
        "customer_tenure": {"type": "number"},
        "geo_distance": {"type": "number"},
        "segment": {"type": ["string", "null"]},
    },
    "required": [
        "transaction_id",
        "customer_id",
        "merchant_id",
        "device_id",
        "card_id",
        "ip_address",
        "amount",
        "currency",
        "device_trust_score",
        "merchant_risk_score",
        "velocity_1m",
        "velocity_1h",
        "chargeback_rate",
        "account_age_days",
        "customer_tenure",
        "geo_distance",
    ],
}


@lru_cache
def get_inference_service() -> InferenceService:
    service = InferenceService()
    get_shutdown_coordinator().register("inference_snapshot", service.flush)
    return service


@lru_cache
def get_feature_service() -> FeatureService:
    return FeatureService()


@lru_cache
def get_redis_stream() -> RedisStream:
    return RedisStream()


@lru_cache
def get_shadow_service() -> ShadowTrafficService:
    return ShadowTrafficService()


@lru_cache
def get_request_contract() -> HttpContractValidator:
    return HttpContractValidator(REQUEST_SCHEMA)


@lru_cache
def get_feedback_service() -> FeedbackService:
    return FeedbackService()


@lru_cache
def get_privacy_service() -> PrivacyService:
    return PrivacyService()


@lru_cache
def get_decision_service() -> DecisionService:
    return DecisionService(get_inference_service())


@lru_cache
def get_console_service() -> ConsoleService:
    return ConsoleService()


@lru_cache
def get_tenant_resolver() -> TenantResolver:
    settings = get_settings()
    mapping = dict(settings.tenant_api_keys)
    try:
        from app.core.crypto_rotate import get_key_manager

        mapping.update(get_key_manager().active_api_keys())
    except Exception:  # pragma: no cover - defensive fallback
        pass
    return TenantResolver(mapping)


def _require_admin(request: Request, resolver: TenantResolver) -> None:
    tenant = resolver.resolve(request.headers)
    guard = get_admin_guard()
    identifier = tenant.api_key or (
        f"ip:{request.client.host}" if request.client else "ip:unknown"
    )
    try:
        guard.record(identifier, success=bool(tenant.api_key))
    except PermissionError:
        get_audit_ledger().append(
            event_id=f"admin-lock:{identifier}",
            payload={"kind": "admin_lockout", "identifier": identifier},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="admin access temporarily locked",
        )
    if not tenant.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="api key required")


@lru_cache
def get_dp_accountant() -> DifferentialPrivacyAccountant:
    settings = get_settings()
    return DifferentialPrivacyAccountant(settings.dp_total_epsilon)


@lru_cache
def get_audit_ledger() -> MerkleLedger:
    return get_ledger()


@lru_cache
def get_lineage() -> LineageEmitter:
    return get_lineage_emitter()


@lru_cache
def get_guardrails() -> SafetySwitch:
    return get_safety_switch()


@lru_cache
def get_ingest_signer() -> IngestSigner:
    return IngestSigner()


def _feature_vector(feature_service: FeatureService, payload: TransactionPayload) -> list[float]:
    return feature_service.to_feature_list(payload.model_dump())


def _dp_metrics(metrics: Dict[str, float], tenant_id: str) -> Dict[str, float]:
    settings = get_settings()
    accountant = get_dp_accountant()
    noisy: Dict[str, float] = {}
    for key, value in metrics.items():
        noisy[key] = laplace_mechanism(
            value,
            epsilon=settings.dp_metrics_epsilon,
            accountant=accountant,
            seed=settings.dp_seed + hash((tenant_id, key)) % 10_000,
        )
    return noisy


def _expected_baseline() -> str:
    return get_settings().api_baseline_hash


def _enforce_baseline(request: Request) -> None:
    expected = _expected_baseline()
    provided = request.headers.get("X-API-Baseline-Hash")
    if not expected or expected == "dev":
        return
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={"error": "missing baseline hash", "expected": expected},
        )
    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={"error": "baseline hash mismatch", "expected": expected, "received": provided},
        )


@router.post("/predict", response_model=PredictionResponse)
async def predict_transaction(
    payload: TransactionPayload,
    request: Request,
    response: Response,
    inference_service: InferenceService = Depends(get_inference_service),
    feature_service: FeatureService = Depends(get_feature_service),
    redis_stream: RedisStream = Depends(get_redis_stream),
    shadow_service: ShadowTrafficService = Depends(get_shadow_service),
    contract: HttpContractValidator = Depends(get_request_contract),
    feedback_service: FeedbackService = Depends(get_feedback_service),
    privacy_service: PrivacyService = Depends(get_privacy_service),
    decision_service: DecisionService = Depends(get_decision_service),
    console_service: ConsoleService = Depends(get_console_service),
    graph_service: GraphFeatureService = Depends(get_graph_feature_service),
    traffic_router: TrafficRouter = Depends(get_traffic_router),
) -> Any:
    settings = get_settings()
    _enforce_baseline(request)
    trace_context = start_trace(dict(request.headers))
    contract(payload.model_dump())
    expectations = DEFAULT_EXPECTATIONS.validate(payload.model_dump())
    if not expectations.passed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=expectations.failures)

    tenant = get_tenant_resolver().resolve(request.headers)
    quota_manager = get_quota_manager()
    quota_decision = quota_manager.check(tenant.tenant_id)
    if not quota_decision.allowed:
        response.headers["Retry-After"] = f"{quota_decision.retry_after:.2f}"
        response.headers["X-RateLimit-Remaining"] = "0"
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"reason": quota_decision.reason or "quota", "tenant": tenant.tenant_id},
        )
    response.headers["X-RateLimit-Remaining"] = f"{quota_decision.remaining:.2f}"
    scheduler = get_sla_scheduler()
    admit_decision = scheduler.admit(tenant.tenant_id)
    if not admit_decision.allowed:
        response.headers["Retry-After"] = f"{admit_decision.retry_after:.2f}"
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"reason": admit_decision.reason or "tenant_backoff", "tenant": tenant.tenant_id},
        )
    event_id = event_identifier(
        trace_context,
        tenant_id=tenant.tenant_id,
        transaction_id=payload.transaction_id,
    )
    enforce_writable(response.headers)
    idempotency_key = request.headers.get("Idempotency-Key")
    store = get_idempotency_store()
    if idempotency_key:
        record = store.get(tenant.tenant_id, idempotency_key)
        if record:
            request.state.active_route = record.route
            response.headers["X-Route-Decision"] = record.route
            response.headers["X-Idempotency-Cache"] = "hit"
            if record.status_code == status.HTTP_200_OK:
                return PredictionResponse(**record.payload)
            if retry_after := record.headers.get("Retry-After"):
                response.headers["Retry-After"] = retry_after
            raise HTTPException(status_code=record.status_code, detail=record.payload)
    features = _feature_vector(feature_service, payload)
    route = traffic_router.select(
        tenant_id=tenant.tenant_id,
        event_id=event_id,
        safe_mode=False,
    )
    request.state.active_route = route
    response.headers["X-Route-Decision"] = route
    prediction = inference_service.predict(features)
    prediction_set = inference_service.online_model.predict_set(
        features, coverage=settings.target_coverage
    )
    decision = decision_service.decide(
        probability=prediction.probability,
        features=features,
        context={**payload.model_dump(), "tenant_id": tenant.tenant_id},
        prediction_set=prediction_set,
        strategy=getattr(payload, "strategy", "consensus"),
    )

    feedback_service.register_prediction(
        event_id=event_id,
        features=features,
        probability=prediction.probability,
        occurred_at=datetime.utcnow(),
        group=payload.segment,
        tenant_id=tenant.tenant_id,
    )

    privacy_service.record_subject_event(
        tenant_id=tenant.tenant_id,
        subject_id=payload.customer_id,
        payload={
            "event_id": event_id,
            "decision": decision.action,
            "probability": prediction.probability,
        },
    )

    ledger = get_audit_ledger()
    ledger.append(
        event_id=event_id,
        payload={
            "transaction_id": payload.transaction_id,
            "tenant_id": tenant.tenant_id,
            "probability": prediction.probability,
            "decision": decision.action,
            "lamport": trace_context.lamport,
        },
    )

    lineage = get_lineage()
    lineage.emit(
        name="inference",
        context=trace_context,
        inputs=[{"name": "transaction", "facets": {"tenant": tenant.tenant_id}}],
        outputs=[{"name": "decision", "facets": {"action": decision.action}}],
        facets=lineage.run_facets(
            {
                "latency_ms": prediction.latency_ms,
                "probability": prediction.probability,
            }
        ),
    )

    graph_metrics = graph_service.update(
        event_id=event_id,
        payload=payload.model_dump(),
        fraud_probability=prediction.probability,
    )

    stream_id = redis_stream.publish(
        {
            "transaction_id": payload.transaction_id,
            "tenant": tenant.tenant_id,
            "customer_id": privacy_service.hash_value(payload.customer_id),
            "fraud_probability": prediction.probability,
            "decision": decision.action,
            "event_id": event_id,
            "trace_id": trace_context.trace_id,
        }
    )
    if stream_id == "":
        retry_after = "2"
        response.headers["Retry-After"] = retry_after
        if idempotency_key:
            store.store_error(
                tenant.tenant_id,
                idempotency_key,
                detail={"reason": "redis_stream_backpressure"},
                route=route,
                headers={"Retry-After": retry_after},
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited", "retry_after": retry_after},
        )

    async with run_tasks(
        [
            TaskSpec(
                name="shadow-record",
                coroutine=lambda: shadow_service.record(
                    headers=request.headers,
                    transaction_id=payload.transaction_id,
                    features=features,
                    probability=prediction.probability,
                    latency_ms=prediction.latency_ms,
                    trace_context=propagate_headers(trace_context),
                ),
            ),
            TaskSpec(
                name="console-publish",
                coroutine=lambda: console_service.publish(
                    {
                        "transaction_id": payload.transaction_id,
                        "tenant_id": tenant.tenant_id,
                        "probability": prediction.probability,
                        "decision": decision.action,
                        "prediction_set": sorted(prediction_set),
                        "latency_ms": prediction.latency_ms,
                        "audit_root": ledger.root(),
                        "guardrail": guardrails.state,
                        "route": route,
                    }
                ),
            ),
        ],
        timeout=settings.fanout_deadline_seconds,
    ):
        pass
    raw_metrics = inference_service.metrics() | {"target_coverage": settings.target_coverage}
    raw_metrics.update({f"graph_{key}": value for key, value in graph_metrics.items()})
    guardrails = get_guardrails().evaluate(
        metrics=raw_metrics,
        drift_metrics=None,
        policy_flags=decision.policy.matched_rules,
        tenant_id=tenant.tenant_id,
    )
    if guardrails.state == "REVIEW":
        decision.action = "review"
        if "safety_switch" not in decision.reasons:
            decision.reasons.append("safety_switch")
        if route != "baseline":
            traffic_router.override_to_baseline()
            route = "baseline"
            request.state.active_route = route

    metrics = _dp_metrics(raw_metrics, tenant.tenant_id)

    router_snapshot = traffic_router.snapshot(safe_mode=guardrails.state == "REVIEW")
    metrics.update(
        {
            "router_baseline_pct": router_snapshot.baseline,
            "router_candidate_pct": router_snapshot.candidate,
            "router_overrides": float(router_snapshot.overrides),
        }
    )
    for name, pct in router_snapshot.routes.items():
        metrics[f"router_{name}_pct"] = pct

    fraud_probability = quantize_prob(prediction.probability)
    response_body = PredictionResponse(
        transaction_id=payload.transaction_id,
        event_id=event_id,
        tenant_id=tenant.tenant_id,
        fraud_probability=fraud_probability,
        prediction_set=sorted(prediction_set),
        decision=decision.action,
        expected_cost=decision.expected_cost,
        threshold=decision.threshold,
        latency_ms=prediction.latency_ms,
        metrics=metrics,
        reasons=decision.reasons + guardrails.reasons,
    )
    if decision.action in {"deny", "review"}:
        receipt = issue_decision_receipt(
            {
                "event_id": event_id,
                "tenant_id": tenant.tenant_id,
                "probability": fraud_probability,
                "decision": decision.action,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        response_body.receipt_id = receipt.identifier
        response.headers["X-Decision-Receipt"] = receipt.signature
        response.headers["X-Decision-Receipt-Id"] = receipt.identifier
    if idempotency_key:
        store.store_success(
            tenant.tenant_id,
            idempotency_key,
            payload=response_body.model_dump(),
            route=route,
            headers={key: value for key, value in response.headers.items() if key in {"Retry-After"}},
        )
        response.headers["X-Idempotency-Cache"] = "stored"

    return response_body


@router.post("/dsar/export", response_model=DsarResponse)
async def dsar_export(
    payload: DsarPayload,
    request: Request,
    privacy_service: PrivacyService = Depends(get_privacy_service),
) -> DsarResponse:
    tenant = get_tenant_resolver().resolve(request.headers)
    tenant_id = payload.tenant_id or tenant.tenant_id
    operator = DSAROperator(salt=privacy_service.hash_value("dsar-mask"))
    records = privacy_service.export_subject(tenant_id=tenant_id, subject_id=payload.subject_id)
    masked = [operator.export({k: str(v) for k, v in record.items()}) for record in records]
    return DsarResponse(subject_id=payload.subject_id, tenant_id=tenant_id, records=masked)


@router.post("/dsar/delete")
async def dsar_delete(
    payload: DsarPayload,
    request: Request,
    response: Response,
    privacy_service: PrivacyService = Depends(get_privacy_service),
) -> Dict[str, str]:
    enforce_writable(response.headers)
    tenant = get_tenant_resolver().resolve(request.headers)
    tenant_id = payload.tenant_id or tenant.tenant_id
    operator = DSAROperator(salt=privacy_service.hash_value("dsar-mask"))
    receipt = operator.delete({"tenant_id": tenant_id, "subject_id": payload.subject_id})
    deleted = privacy_service.delete_subject(tenant_id=tenant_id, subject_id=payload.subject_id)
    status_flag = "deleted" if deleted else "legal_hold"
    receipt.update({"status": status_flag})
    return receipt


@router.get("/consent", response_model=ConsentResponse)
async def consent_version(
    privacy_service: PrivacyService = Depends(get_privacy_service),
) -> ConsentResponse:
    return ConsentResponse(version=privacy_service.consent_version())


@router.post("/consent", response_model=ConsentResponse)
async def update_consent(
    payload: ConsentPayload,
    privacy_service: PrivacyService = Depends(get_privacy_service),
) -> ConsentResponse:
    return ConsentResponse(version=privacy_service.update_consent(payload.version))


@router.post("/ingest")
async def ingest_signed(
    payload: TransactionPayload,
    request: Request,
    signer: IngestSigner = Depends(get_ingest_signer),
    privacy_service: PrivacyService = Depends(get_privacy_service),
    redis_stream: RedisStream = Depends(get_redis_stream),
) -> Dict[str, str]:
    try:
        signer.verify(request.headers, payload.transaction_id)
    except IngestSignatureError as exc:  # pragma: no cover - deterministic branch
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    contract = get_request_contract()
    contract(payload.model_dump())
    expectations = DEFAULT_EXPECTATIONS.validate(payload.model_dump())
    if not expectations.passed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=expectations.failures)
    tenant = get_tenant_resolver().resolve(request.headers)
    privacy_service.record_subject_event(
        tenant_id=tenant.tenant_id,
        subject_id=payload.customer_id,
        payload={"transaction_id": payload.transaction_id, "ingested": True},
    )
    redis_stream.publish({
        "transaction_id": payload.transaction_id,
        "tenant": tenant.tenant_id,
        "ingest": True,
    })
    return {"status": "accepted", "transaction_id": payload.transaction_id}


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    payload: FeedbackPayload,
    request: Request,
    response: Response,
    inference_service: InferenceService = Depends(get_inference_service),
    feedback_service: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    _enforce_baseline(request)
    enforce_writable(response.headers)
    tenant = get_tenant_resolver().resolve(request.headers)
    tenant_id = payload.tenant_id or tenant.tenant_id
    result = feedback_service.record_feedback(
        event_id=payload.event_id,
        label=payload.label,
        observed_at=payload.observed_at,
        group=payload.group,
        tenant_id=tenant_id,
    )
    updated = False
    if result.applied and result.features is not None:
        inference_service.partial_fit(
            result.features,
            result.label,
            sample_weight=result.sample_weight,
            group=result.group,
        )
        updated = True
    return FeedbackResponse(
        event_id=payload.event_id,
        tenant_id=tenant_id,
        applied=result.applied,
        updated=updated,
        delay_seconds=result.delay_seconds,
        sample_weight=result.sample_weight,
    )


@router.post("/decide", response_model=DecisionResponse)
async def decide_transaction(
    payload: DecisionPayload,
    request: Request,
    response: Response,
    inference_service: InferenceService = Depends(get_inference_service),
    feature_service: FeatureService = Depends(get_feature_service),
    decision_service: DecisionService = Depends(get_decision_service),
    contract: HttpContractValidator = Depends(get_request_contract),
) -> DecisionResponse:
    _enforce_baseline(request)
    enforce_writable(response.headers)
    contract(payload.model_dump())
    tenant = get_tenant_resolver().resolve(request.headers)
    features = _feature_vector(feature_service, payload)
    prediction = inference_service.predict(features)
    prediction_set = inference_service.online_model.predict_set(features)
    decision = decision_service.decide(
        probability=prediction.probability,
        features=features,
        context={**payload.model_dump(), "tenant_id": tenant.tenant_id},
        prediction_set=prediction_set,
        strategy=payload.strategy,
    )
    return DecisionResponse(
        transaction_id=payload.transaction_id,
        tenant_id=tenant.tenant_id,
        action=decision.action,
        expected_cost=decision.expected_cost,
        reasons=decision.reasons,
        probability=prediction.probability,
        prediction_set=sorted(prediction_set),
        threshold=decision.threshold,
    )


@router.post("/explain", response_model=ExplainResponse)
async def explain_transaction(
    payload: ExplainPayload,
    request: Request,
    inference_service: InferenceService = Depends(get_inference_service),
    feature_service: FeatureService = Depends(get_feature_service),
) -> ExplainResponse:
    _ = get_tenant_resolver().resolve(request.headers)
    features = _feature_vector(feature_service, payload)
    settings = getattr(inference_service, "settings", get_settings())
    explanation = inference_service.online_model.explain(
        features,
        threshold=settings.inference_threshold,
        bounds=[(0.0, float("inf"))] * len(features),
    )
    contributions = dict(
        zip(feature_service.feature_names, explanation["contributions"], strict=False)
    )
    return ExplainResponse(
        event_id=payload.event_id,
        bias=explanation["bias"],
        probability=explanation["probability"],
        contributions=contributions,
        counterfactual=explanation["counterfactual"],
    )


@router.get("/audit/proof/{event_id}", response_model=AuditProofResponse)
async def audit_proof(event_id: str, ledger: MerkleLedger = Depends(get_audit_ledger)) -> AuditProofResponse:
    proof = ledger.proof(event_id)
    anchor = (
        ledger.anchor_path.read_text(encoding="utf-8")
        if hasattr(ledger, "anchor_path") and ledger.anchor_path.exists()
        else ""
    )
    return AuditProofResponse(
        event_id=event_id,
        root=ledger.root(),
        proof=[{"position": item.position, "hash": item.hash} for item in proof],
        anchor=anchor,
    )


@router.get("/metrics")
async def get_metrics(
    request: Request,
    inference_service: InferenceService = Depends(get_inference_service),
) -> Dict[str, float]:
    tenant = get_tenant_resolver().resolve(request.headers)
    metrics = inference_service.metrics()
    startup = get_startup_state()
    metrics["startup_time_ms"] = startup.startup_time_ms
    metrics["startup_ready"] = 1.0 if startup.ready else 0.0
    return _dp_metrics(metrics, tenant.tenant_id)


@router.get("/readyz")
async def readyz() -> Dict[str, Any]:
    state = get_startup_state()
    if not state.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "ready": False,
                "startup_time_ms": state.startup_time_ms,
                "error": state.error or "startup budget exceeded",
            },
        )
    return {"ready": True, "startup_time_ms": state.startup_time_ms}


@router.get("/console", response_class=HTMLResponse)
async def console_index() -> HTMLResponse:
    settings = get_settings()
    index_path = settings.console_static_path / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="console not built")
    return HTMLResponse(index_path.read_text())


@router.get("/console/stream")
async def console_stream(
    request: Request,
    console_service: ConsoleService = Depends(get_console_service),
) -> StreamingResponse:
    async def event_stream() -> Iterable[str]:
        async for event in console_service.stream(dict(request.headers)):
            yield event

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/doctor")
async def doctor() -> Dict[str, Any]:
    report = doctor_checks()
    if not isinstance(report, dict):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="invalid report")
    return report


@router.get("/cache", response_model=CacheSummaryResponse)
async def cache_summary(
    request: Request,
    tenant_resolver: TenantResolver = Depends(get_tenant_resolver),
) -> CacheSummaryResponse:
    tenant = tenant_resolver.resolve(request.headers)
    if not tenant.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="api key required")
    return CacheSummaryResponse(caches=get_cache_registry().summary())


@router.post("/diag/snapshot", response_model=DiagResponse)
async def diag_snapshot(
    request: Request,
    tenant_resolver: TenantResolver = Depends(get_tenant_resolver),
) -> DiagResponse:
    tenant = tenant_resolver.resolve(request.headers)
    if not tenant.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="api key required")
    bundle = build_bundle(None)
    return DiagResponse(path=str(bundle))


def _drain_payload(status) -> DrainStatusResponse:
    return DrainStatusResponse(
        state=status.state,
        phase=status.phase.value if hasattr(status.phase, 'value') else str(status.phase),
        reason=status.reason,
        seconds_since=status.seconds_since,
    )


@router.post("/drain/start", response_model=DrainStatusResponse)
async def drain_start(
    command: DrainCommand,
    request: Request,
    tenant_resolver: TenantResolver = Depends(get_tenant_resolver),
) -> DrainStatusResponse:
    _require_admin(request, tenant_resolver)
    status_obj = get_drain_manager().start(command.reason)
    return _drain_payload(status_obj)


@router.post("/drain/stop", response_model=DrainStatusResponse)
async def drain_stop(
    request: Request,
    tenant_resolver: TenantResolver = Depends(get_tenant_resolver),
) -> DrainStatusResponse:
    _require_admin(request, tenant_resolver)
    status_obj = get_drain_manager().stop()
    return _drain_payload(status_obj)


@router.get("/drain/status", response_model=DrainStatusResponse)
async def drain_status() -> DrainStatusResponse:
    return _drain_payload(get_drain_manager().status())


@router.get("/migrate/status", response_model=MigrationStatus)
async def migrate_status(service: MigrationService = Depends(get_migration_service)) -> MigrationStatus:
    return MigrationStatus(**service.status())


@router.post("/migrate/cutover", response_model=MigrationStatus)
async def migrate_cutover(
    command: MigrationCommand,
    service: MigrationService = Depends(get_migration_service),
) -> MigrationStatus:
    try:
        if command.action == "start":
            service.begin_dual_write(command.actor_id)
        elif command.action == "backfill":
            service.begin_backfill(command.actor_id)
        elif command.action == "validate":
            service.mark_validate(command.actor_id)
        elif command.action == "finalize":
            service.finalize(command.actor_id)
        else:
            service.commit_cutover(command.actor_id)
    except LeadershipError as exc:  # pragma: no cover - exercised in integration tests
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MigrationStatus(**service.status())


@router.post("/migrate/rollback", response_model=MigrationStatus)
async def migrate_rollback(
    command: MigrationCommand,
    service: MigrationService = Depends(get_migration_service),
) -> MigrationStatus:
    try:
        service.rollback(command.actor_id)
    except LeadershipError as exc:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return MigrationStatus(**service.status())


@router.get("/runtime/status", response_model=RuntimeAckResponse)
async def runtime_status() -> RuntimeAckResponse:
    state = get_crashloop_breaker().state()
    return RuntimeAckResponse(tripped=state.tripped, reason=state.reason)


@router.post("/runtime/ack", response_model=RuntimeAckResponse)
async def runtime_ack(
    request: Request,
    tenant_resolver: TenantResolver = Depends(get_tenant_resolver),
) -> RuntimeAckResponse:
    _require_admin(request, tenant_resolver)
    state = get_crashloop_breaker().acknowledge()
    return RuntimeAckResponse(tripped=state.tripped, reason=state.reason)
