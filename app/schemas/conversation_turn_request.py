"""Request schema for /conversation-turn route."""

from typing import Literal

from pydantic import BaseModel, Field


class ConversationTurnRequest(BaseModel):
    """Request model for multi-turn conversation.

    Contains conversation history, current message, and context strategy selection.
    """

    conversation_id: str = Field(
        ..., min_length=1, description="Unique identifier for this conversation"
    )

    history: list[str] = Field(
        default_factory=list, description="List of previous messages in the conversation"
    )

    message: str = Field(..., min_length=1, description="Current message to process")

    context_strategy: Literal["full", "sliding_window", "summarized"] = Field(
        ..., description="Context strategy to apply for this turn"
    )
