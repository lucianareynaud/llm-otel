"""Request schema for /answer-routed route."""

from pydantic import BaseModel, Field


class AnswerRoutedRequest(BaseModel):
    """Request model for routed answer generation.

    Simple request containing only the message to answer.
    """

    message: str = Field(
        ..., min_length=1, description="The message to answer with routing-based model selection"
    )
