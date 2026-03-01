"""Route handler for /answer-routed endpoint.

This route demonstrates routing-based model selection with explicit
routing metadata in the response.
"""

from fastapi import APIRouter

from app.schemas.answer_routed_request import AnswerRoutedRequest
from app.schemas.answer_routed_response import AnswerRoutedResponse
from app.services.routing import determine_complexity
from gateway.client import call_llm

router = APIRouter()


@router.post("/answer-routed", response_model=AnswerRoutedResponse)
def answer_routed(request: AnswerRoutedRequest) -> AnswerRoutedResponse:
    """Generate an answer using routing-based model selection."""
    complexity, recommended_tier, needs_escalation = determine_complexity(request.message)

    result = call_llm(
        prompt=request.message,
        model_tier=recommended_tier,
        route_name="/answer-routed",
        metadata={
            "complexity": complexity,
            "routing_decision": recommended_tier,
            "needs_escalation": needs_escalation,
        },
    )

    return AnswerRoutedResponse(
        answer=result.text,
        selected_model=result.selected_model,
        routing_decision=recommended_tier,
    )