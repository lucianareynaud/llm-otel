"""Route handler for /classify-complexity endpoint.

This route represents the cheapest operational pattern in the reference app,
optimized for short structured outputs.
"""

from fastapi import APIRouter

from app.schemas.classify_complexity_request import ClassifyComplexityRequest
from app.schemas.classify_complexity_response import ClassifyComplexityResponse
from app.services.routing import determine_complexity

router = APIRouter()


@router.post("/classify-complexity", response_model=ClassifyComplexityResponse)
def classify_complexity(request: ClassifyComplexityRequest) -> ClassifyComplexityResponse:
    """Classify message complexity and recommend a model tier.

    This is the cheapest route in the app, designed for fast classification
    decisions that can route subsequent requests to appropriate model tiers.

    Args:
        request: The classification request containing the message

    Returns:
        Classification response with complexity, recommended tier, and escalation flag
    """
    complexity, recommended_tier, needs_escalation = determine_complexity(request.message)

    return ClassifyComplexityResponse(
        complexity=complexity, recommended_tier=recommended_tier, needs_escalation=needs_escalation
    )
