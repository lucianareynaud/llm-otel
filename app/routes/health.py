"""Infrastructure health endpoints.

These endpoints are intentionally minimal and contain no business logic,
no gateway imports, and no OTel imports. They exist solely so that
orchestrators (Kubernetes, Docker Compose, load balancers) can probe
liveness and readiness without hitting authenticated routes.

Neither endpoint requires the X-API-Key header once auth middleware is
added in spec 007 — both are explicitly exempted.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_ready: bool = False


def set_ready(value: bool) -> None:
    """Set the readiness flag.

    Called from the FastAPI lifespan handler: True after startup completes,
    False as the first action during shutdown so the load balancer can drain
    traffic before teardown proceeds.
    """
    global _ready
    _ready = value


@router.get("/healthz")
def healthz() -> JSONResponse:
    """Liveness probe — always returns 200.

    A 200 here means the process is alive and the event loop is responsive.
    It does not guarantee that upstream dependencies are available.
    """
    return JSONResponse({"status": "ok"})


@router.get("/readyz")
def readyz() -> JSONResponse:
    """Readiness probe — returns 200 when startup is complete, 503 otherwise.

    Returns 503 during startup (before lifespan yield) and during shutdown
    (after set_ready(False) is called). Load balancers should stop routing
    traffic when this returns 503.
    """
    if _ready:
        return JSONResponse({"status": "ready"})
    return JSONResponse({"status": "not_ready"}, status_code=503)
