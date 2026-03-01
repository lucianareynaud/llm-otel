"""Centralized GenAI semantic convention attribute strings for the LLM gateway.

WHY THIS MODULE EXISTS
──────────────────────
The OpenTelemetry GenAI semantic conventions are currently at Development
stability (as of opentelemetry-semantic-conventions 0.60b1). Development-
stability conventions can rename, add, or remove attributes between releases
without a deprecation window. Direct imports of string constants from
``opentelemetry.semconv._incubating.*`` scattered across client.py and
telemetry.py would mean that a convention rename requires hunting for all
usages across the codebase.

This module is the single place in the entire gateway where OTel attribute
name strings are defined. All other gateway modules import from here, never
from ``opentelemetry.semconv`` directly. When the GenAI spec evolves:

  1. Update the ATTR_* constants in this file.
  2. If a rename occurred, add the old→new pair to ``_PENDING_RENAMES``.
  3. ``resolve_attrs()`` handles dual-emission automatically for callers
     that set ``OTEL_SEMCONV_STABILITY_OPT_IN``.

Nothing else in the codebase needs to change.

OTEL_SEMCONV_STABILITY_OPT_IN
──────────────────────────────
This environment variable is the OpenTelemetry-recommended mechanism for
managing attribute name migrations. The GenAI-specific values
(https://opentelemetry.io/docs/specs/semconv/gen-ai/openai/) are:

  (not set)                      Default. Emit v1.36.0 conventions only
                                 (gen_ai.system = "openai").

  gen_ai_latest_experimental     Emit the latest experimental GenAI
                                 conventions only (gen_ai.provider.name = "openai").
                                 Do NOT emit v1.36.0 attributes.

  gen_ai_latest_experimental/dup Emit BOTH old (gen_ai.system) and new
                                 (gen_ai.provider.name) attributes simultaneously.
                                 Use during a migration window so dashboards
                                 built on either name keep working.

The current active migration is:
  gen_ai.system  →  gen_ai.provider.name
  (v1.36.0 legacy)  (latest experimental, MUST per OpenAI semconv spec)

This is in ``_PENDING_RENAMES`` and is applied by ``resolve_attrs()``.

DESIGN NOTES
─────────────
- All attribute name strings are plain str constants, not imported from the
  OTel package. This decouples the codebase from the ``_incubating`` import
  path, which is explicitly unstable.
- Value constants (e.g. "openai", "chat") follow the same pattern: one
  source of truth, no inline string literals elsewhere in the gateway.
- ``resolve_attrs()`` is a pure function — no side effects, easy to test.
"""

from __future__ import annotations

import os

from opentelemetry.util.types import AttributeValue as AttrValue

# ── Provider / System ────────────────────────────────────────────────────────
# v1.36.0 legacy attribute — emitted by default for backwards compatibility.
ATTR_GEN_AI_SYSTEM = "gen_ai.system"
# Latest-experimental attribute — MUST be set per the current OpenAI semconv spec.
# https://opentelemetry.io/docs/specs/semconv/gen-ai/openai/
ATTR_GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
VAL_GEN_AI_SYSTEM_OPENAI = "openai"

# ── Operation ────────────────────────────────────────────────────────────────
ATTR_GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
VAL_GEN_AI_OPERATION_CHAT = "chat"

# ── Request attributes ───────────────────────────────────────────────────────
ATTR_GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
ATTR_GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"

# ── Response attributes ──────────────────────────────────────────────────────
ATTR_GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"

# ── Token usage ──────────────────────────────────────────────────────────────
ATTR_GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
ATTR_GEN_AI_TOKEN_TYPE = "gen_ai.token.type"
VAL_GEN_AI_TOKEN_TYPE_INPUT = "input"
VAL_GEN_AI_TOKEN_TYPE_OUTPUT = "output"

# ── Metric instrument names ───────────────────────────────────────────────────
# Standard GenAI histogram names from the OTel metrics spec:
# https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/
METRIC_TOKEN_USAGE = "gen_ai.client.token.usage"
METRIC_OPERATION_DURATION = "gen_ai.client.operation.duration"

# ── OTEL_SEMCONV_STABILITY_OPT_IN migration support ─────────────────────────

_OPT_IN_LATEST = "gen_ai_latest_experimental"
_OPT_IN_LATEST_DUP = "gen_ai_latest_experimental/dup"

# Active renames from v1.36.0 → latest experimental.
# Source: https://opentelemetry.io/docs/specs/semconv/gen-ai/openai/
# "gen_ai.provider.name MUST be set to 'openai'" (supersedes gen_ai.system).
_PENDING_RENAMES: dict[str, str] = {
    ATTR_GEN_AI_SYSTEM: ATTR_GEN_AI_PROVIDER_NAME,
}


def _opt_in_mode() -> str | None:
    """Read and parse OTEL_SEMCONV_STABILITY_OPT_IN for GenAI-relevant tokens.

    Returns the active gen_ai opt-in mode string, or None if not set.
    The env var is a comma-separated list; we extract only the genai token.
    """
    raw = os.getenv("OTEL_SEMCONV_STABILITY_OPT_IN", "")
    for token in raw.split(","):
        stripped = token.strip()
        if stripped in (_OPT_IN_LATEST, _OPT_IN_LATEST_DUP):
            return stripped
    return None


def resolve_attrs(attrs: dict[str, AttrValue]) -> dict[str, AttrValue]:
    """Apply OTEL_SEMCONV_STABILITY_OPT_IN dual-emission to a span attribute dict.

    In normal mode (env var not set): returns ``attrs`` unchanged.
    Default behavior emits v1.36.0 conventions (gen_ai.system).

    In ``gen_ai_latest_experimental/dup`` mode: for each renamed attribute
    present in ``attrs``, adds the new attribute name alongside the old one.
    Both names are emitted during a migration window so dashboards built on
    either name continue to function.

    In ``gen_ai_latest_experimental`` mode: replaces the old name with the
    new name for each renamed attribute. Backends receive only the new
    convention names (gen_ai.provider.name for OpenAI).

    Args:
        attrs: Dict of span or metric attributes using current attribute names.

    Returns:
        New dict with dual-emitted or replaced names according to opt-in mode.
        Returns the original dict unchanged if no migration is active.
    """
    if not _PENDING_RENAMES:
        return attrs

    mode = _opt_in_mode()
    if mode is None:
        return attrs

    result = dict(attrs)
    for old_attr, new_attr in _PENDING_RENAMES.items():
        if old_attr not in result:
            continue
        if mode == _OPT_IN_LATEST_DUP:
            result[new_attr] = result[old_attr]
        elif mode == _OPT_IN_LATEST:
            result[new_attr] = result.pop(old_attr)

    return result
