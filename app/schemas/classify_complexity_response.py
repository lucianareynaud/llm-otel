"""Response schema for /classify-complexity route."""

from typing import Literal

from pydantic import BaseModel, Field


class ClassifyComplexityResponse(BaseModel):
    """Response model for complexity classification.

    This schema represents the output of the cheapest route in the app,
    designed for short structured outputs that classify request complexity
    and recommend a model tier.
    """

    complexity: Literal["simple", "medium", "complex"] = Field(
        ..., description="Classified complexity level of the input message"
    )

    recommended_tier: Literal["cheap", "expensive"] = Field(
        ..., description="Recommended model tier based on complexity"
    )

    needs_escalation: bool = Field(
        ..., description="Whether the request needs escalation to a more capable model"
    )
