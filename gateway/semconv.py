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
managing attribute name migrations across convention stability transitions.
The three supported modes for GenAI (see https://opentelemetry.io/docs/specs/semconv/gen-ai/):

  (not set)        Default. Emit current attribute names only.

  genai            Emit only the new attribute names for any renamed attributes.
                   Use this after a migration is complete to stop emitting old names.

  genai/dup        Emit both old and new names for any renamed attributes.
                   Use this during a migration window so backends indexing either
                   name continue to work while dashboards are being updated.

Currently ``_PENDING_RENAMES`` is empty because no GenAI attribute has been
renamed in the 0.60b1 → current range. The mechanism is live and tested so
that the next rename is a one-line addition to ``_PENDING_RENAMES``.

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

# ── Provider / System ────────────────────────────────────────────────────────
ATTR_GEN_AI_SYSTEM = "gen_ai.system"
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

# ── OTEL_SEMCONV_STABILITY_OPT_IN migration support ─────────────────────────

_OPT_IN_GENAI = "genai"
_OPT_IN_GENAI_DUP = "genai/dup"

# Attribute renames that have occurred between the pinned convention version
# and the current spec. Format: {old_attr_name: new_attr_name}.
#
# Currently empty — no GenAI attribute has been renamed since 0.60b1.
# When a rename is finalized in the spec, add it here:
#   e.g. _PENDING_RENAMES = {"gen_ai.system": "gen_ai.provider.name"}
_PENDING_RENAMES: dict[str, str] = {}


def _opt_in_mode() -> str | None:
    """Read and parse the OTEL_SEMCONV_STABILITY_OPT_IN env var for GenAI tokens.

    Returns the active genai opt-in mode string, or None if not set.
    The env var may be a comma-separated list of tokens for multiple semconv
    families (e.g. "http,genai/dup"). We extract only the genai-relevant token.
    """
    raw = os.getenv("OTEL_SEMCONV_STABILITY_OPT_IN", "")
    for token in raw.split(","):
        stripped = token.strip()
        if stripped in (_OPT_IN_GENAI, _OPT_IN_GENAI_DUP):
            return stripped
    return None


def resolve_attrs(attrs: dict[str, object]) -> dict[str, object]:
    """Apply OTEL_SEMCONV_STABILITY_OPT_IN dual-emission to a span attribute dict.

    In normal mode (env var not set): returns ``attrs`` unchanged.

    In ``genai/dup`` mode: for each renamed attribute present in ``attrs``,
    adds the new attribute name alongside the old one. The backend receives
    both names during the migration window, so dashboards built on either
    name continue to function.

    In ``genai`` mode: for each renamed attribute present in ``attrs``,
    replaces the old name with the new name. Use after a migration is complete.

    This function is intentionally a no-op when ``_PENDING_RENAMES`` is empty,
    which is the current state. The mechanism is wired and tested so that
    adding a rename to ``_PENDING_RENAMES`` is the only change needed during
    a future migration.

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
        if mode == _OPT_IN_GENAI_DUP:
            result[new_attr] = result[old_attr]
        elif mode == _OPT_IN_GENAI:
            result[new_attr] = result.pop(old_attr)

    return result
