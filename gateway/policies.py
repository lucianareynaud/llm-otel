"""Route-specific policy configuration for gateway-backed routes.

This module owns bounded policy definitions for routes that currently use
the gateway. Policies remain hardcoded, inspectable, and simple.
"""

from dataclasses import dataclass
from typing import Literal

ModelTier = Literal["cheap", "expensive"]


@dataclass(frozen=True)
class RoutePolicy:
    """Policy configuration for a gateway-backed route."""

    max_output_tokens: int
    retry_attempts: int
    cache_enabled: bool
    model_for_tier: dict[ModelTier, str]


_ROUTE_POLICIES: dict[str, RoutePolicy] = {
    "/answer-routed": RoutePolicy(
        max_output_tokens=500,
        retry_attempts=2,
        cache_enabled=False,
        model_for_tier={
            "cheap": "gpt-4o-mini",
            "expensive": "gpt-4o",
        },
    ),
    "/conversation-turn": RoutePolicy(
        max_output_tokens=500,
        retry_attempts=2,
        cache_enabled=False,
        model_for_tier={
            "cheap": "gpt-4o-mini",
            "expensive": "gpt-4o",
        },
    ),
}


def get_route_policy(route_name: str) -> RoutePolicy:
    """Return the policy configuration for a gateway-backed route.

    Args:
        route_name: Route path such as ``/answer-routed``.

    Returns:
        The configured RoutePolicy for the route.

    Raises:
        ValueError: If the route has no gateway policy.
    """
    if route_name not in _ROUTE_POLICIES:
        available_routes = ", ".join(sorted(_ROUTE_POLICIES.keys()))
        raise ValueError(
            f"No gateway policy defined for route: {route_name}. "
            f"Available routes: {available_routes}"
        )

    return _ROUTE_POLICIES[route_name]


def get_model_for_tier(route_name: str, tier: ModelTier) -> str:
    """Resolve the concrete model name for a logical tier on a route.

    Args:
        route_name: Route path such as ``/answer-routed``.
        tier: Logical model tier.

    Returns:
        Concrete model name configured for that route and tier.

    Raises:
        ValueError: If the tier is not configured for the route.
    """
    policy = get_route_policy(route_name)

    if tier not in policy.model_for_tier:
        available_tiers = ", ".join(sorted(policy.model_for_tier.keys()))
        raise ValueError(
            f"Tier '{tier}' not configured for route {route_name}. "
            f"Available tiers: {available_tiers}"
        )

    return policy.model_for_tier[tier]