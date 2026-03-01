"""Request schema for /classify-complexity route."""

from pydantic import BaseModel, Field


class ClassifyComplexityRequest(BaseModel):
    """Request model for complexity classification.

    Simple request containing only the message to classify.
    """

    message: str = Field(..., min_length=1, description="The message to classify for complexity")
