"""Deterministic cost estimation from local pricing configuration.

This module owns cost estimation for gateway-backed provider calls based on
token counts and local inspectable pricing data.

Pricing is intentionally hardcoded for reproducibility in the MVP.
"""

from copy import deepcopy

TOKENS_PER_MILLION = 1_000_000

# Local pricing snapshot for the current provider.
# Prices are in USD per 1M tokens.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-5-mini": {
        "input_per_1m": 0.25,
        "output_per_1m": 2.00,
    },
    "gpt-5.2": {
        "input_per_1m": 1.75,
        "output_per_1m": 14.00,
    },
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate request cost from model and token counts.

    Cost is calculated as:

        (tokens_in / 1_000_000 * input_per_1m)
        + (tokens_out / 1_000_000 * output_per_1m)

    Args:
        model: Resolved model name.
        tokens_in: Number of input tokens.
        tokens_out: Number of output tokens.

    Returns:
        Estimated cost in USD.

    Raises:
        ValueError: If the model is unknown or token counts are negative.
    """
    if model not in MODEL_PRICING:
        raise ValueError(f"Unknown model for cost estimation: {model}")

    if tokens_in < 0 or tokens_out < 0:
        raise ValueError(
            f"Token counts must be non-negative. Got tokens_in={tokens_in}, "
            f"tokens_out={tokens_out}."
        )

    pricing = MODEL_PRICING[model]

    input_cost = (tokens_in / TOKENS_PER_MILLION) * pricing["input_per_1m"]
    output_cost = (tokens_out / TOKENS_PER_MILLION) * pricing["output_per_1m"]

    return input_cost + output_cost


def get_pricing() -> dict[str, dict[str, float]]:
    """Return a safe copy of the current local pricing configuration."""
    return deepcopy(MODEL_PRICING)