"""Route handler for /conversation-turn endpoint.

This route demonstrates multi-turn conversation with explicit context
strategy application and token usage tracking.
"""

from fastapi import APIRouter

from app.schemas.conversation_turn_request import ConversationTurnRequest
from app.schemas.conversation_turn_response import ConversationTurnResponse
from app.services.context_manager import prepare_context
from gateway.client import call_llm

router = APIRouter()


@router.post("/conversation-turn", response_model=ConversationTurnResponse)
def conversation_turn(request: ConversationTurnRequest) -> ConversationTurnResponse:
    """Process a conversation turn with context strategy application."""
    prepared_context, context_tokens_used = prepare_context(
        history=request.history,
        message=request.message,
        strategy=request.context_strategy,
    )

    turn_index = len(request.history)

    result = call_llm(
        prompt=prepared_context,
        model_tier="expensive",
        route_name="/conversation-turn",
        metadata={
            "conversation_id": request.conversation_id,
            "turn_index": turn_index,
            "context_strategy": request.context_strategy,
            "context_strategy_applied": request.context_strategy,
            "context_tokens_used": context_tokens_used,
        },
    )

    return ConversationTurnResponse(
        answer=result.text,
        turn_index=turn_index,
        context_tokens_used=context_tokens_used,
        context_strategy_applied=request.context_strategy,
    )