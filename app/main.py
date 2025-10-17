from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.middleware import install_api_middleware
from app.api.routes import router as api_router, get_inference_service, get_redis_stream
from app.core.config import get_settings
from app.core.http_hardening import install_http_hardening
from app.core.versioning import verify_artifacts
from app.core.self_integrity import get_integrity_monitor
from app.core.staleness import get_staleness_monitor
from app.core.config_invariants import validate_config_invariants
from app.core.shutdown import get_shutdown_coordinator
from app.core.startup import get_startup_state, warm_startup
from app.core.crashloop import get_crashloop_breaker
from app.services.redis_stream import RedisStream
from app.core.env_invariants import enforce_environment_invariants
from app.core.fs_perms import enforce_filesystem_permissions
from app.core.reload import install_reload_handler
from app.core.leak_sentinel import get_leak_sentinel
from app.core.egress_guard import configure_guard


def create_application() -> FastAPI:
    enforce_environment_invariants()
    enforce_filesystem_permissions()
    verify_artifacts()
    validate_config_invariants()
    get_crashloop_breaker().record_boot()
    settings = get_settings()
    if getattr(settings, "egress_guard_enabled", False):
        configure_guard(settings.egress_allowlist)
    application = FastAPI(title=settings.project_name)
    install_http_hardening(application)
    install_api_middleware(application)
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    get_shutdown_coordinator().install()
    install_reload_handler()
    get_leak_sentinel().start()
    get_integrity_monitor().verify_once()
    get_integrity_monitor().start()
    staleness = get_staleness_monitor()
    staleness.evaluate()
    staleness.start()

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        application.mount("/static", StaticFiles(directory=static_dir), name="static")
    if settings.console_static_path.exists():
        application.mount(
            "/console", StaticFiles(directory=settings.console_static_path), name="console-assets"
        )

    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    @application.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        redis_stream: RedisStream = Depends(get_redis_stream),
    ) -> Any:
        recent_predictions = redis_stream.latest()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "project_name": settings.project_name,
                "latency_budget": settings.latency_budget_ms,
                "threshold": settings.inference_threshold,
                "predictions": recent_predictions,
            },
        )

    @application.get("/health")
    async def health(inference_service=Depends(get_inference_service)) -> dict[str, Any]:
        _ = inference_service.metrics()
        return {"status": "ok"}

    @application.get("/ready")
    async def ready() -> dict[str, Any]:
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
        monitor = get_staleness_monitor()
        if not monitor.evaluate():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"ready": False, "error": "model stale", "stale": True},
            )
        if not get_leak_sentinel().healthy():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"ready": False, "error": "leak sentinel alarm"},
            )
        return {"ready": True, "startup_time_ms": state.startup_time_ms}

    return application


app = create_application()


@app.on_event("startup")
async def _warm_startup() -> None:
    warm_startup()
