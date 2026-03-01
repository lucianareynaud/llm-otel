"""Response schema for /answer-routed route."""

from typing import Literal

from pydantic import BaseModel, Field


class AnswerRoutedResponse(BaseModel):
    """Response model for routed answer generation.

    This schema exposes routing decisions explicitly, making model selection
    behavior inspectable and measurable for cost analysis.
    """

    answer: str = Field(..., description="Generated answer to the input message")

    selected_model: str = Field(
        ..., description="The actual model that was selected for this request"
    )

    routing_decision: Literal["cheap", "expensive"] = Field(
        ..., description="The routing decision that determined model selection"
    )
