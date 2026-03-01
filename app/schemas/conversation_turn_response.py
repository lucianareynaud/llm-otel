"""Response schema for /conversation-turn route."""

from typing import Literal

from pydantic import BaseModel, Field


class ConversationTurnResponse(BaseModel):
    """Response model for multi-turn conversation.

    This schema exposes context strategy behavior and token usage explicitly,
    making context window growth measurable for cost analysis.
    """

    answer: str = Field(..., description="Generated answer for this conversation turn")

    turn_index: int = Field(
        ..., ge=0, description="Zero-based index of this turn in the conversation"
    )

    context_tokens_used: int = Field(
        ..., ge=0, description="Estimated number of tokens used for context in this turn"
    )

    context_strategy_applied: Literal["full", "sliding_window", "summarized"] = Field(
        ..., description="The context strategy that was applied for this turn"
    )
