# Design: 005 Real Model Identifiers and Pricing

## Scope
Two files, two constants each. This is a search-and-replace with verified values —
not a refactor. The layering does not change.

---

## gateway/cost_model.py

Replace the `MODEL_PRICING` dict keys and values:

```python
# Source: https://platform.openai.com/docs/models  — retrieved <DATE>
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
    "gpt-4o":      {"input_per_1m": 2.50,  "output_per_1m": 10.00},
}
```

No other logic changes. `estimate_cost()` receives the model string from `call_llm()` —
the function signature and arithmetic are correct as-is.

---

## gateway/policies.py

Update the `model_for_tier` field in both `RoutePolicy` entries:

```python
_ROUTE_POLICIES: dict[str, RoutePolicy] = {
    "/answer-routed": RoutePolicy(
        model_for_tier={"cheap": "gpt-4o-mini", "expensive": "gpt-4o"},
        ...
    ),
    "/conversation-turn": RoutePolicy(
        model_for_tier={"cheap": "gpt-4o-mini", "expensive": "gpt-4o"},
        ...
    ),
}
```

The `RoutePolicy` frozen dataclass structure is unchanged.

---

## Model mapping rationale

| Tier      | Model        | Reason |
|-----------|--------------|--------|
| cheap     | gpt-4o-mini  | Lowest-cost GPT-4 class model; handles simple and medium queries |
| expensive | gpt-4o       | Full GPT-4o; used for complex queries that require reasoning depth |

Both models are available via `client.responses.create(model=...)` with the exact strings above.

---

## Test updates

`tests/test_gateway.py` and `tests/test_routes.py` contain string assertions like
`assert result.selected_model == "gpt-5-mini"`. These must be updated to `"gpt-4o-mini"`
and `"gpt-4o"` respectively. No mock logic changes — only the expected string values.
