"""Tests for gateway.semconv: attribute constants and resolve_attrs() behavior.

These tests verify the OTEL_SEMCONV_STABILITY_OPT_IN dual-emission mechanism
and the contract that all gen_ai.* attribute strings are defined in one place.

The mechanism is currently a no-op because _PENDING_RENAMES is empty.
The tests use monkeypatch to inject a synthetic rename so the dual-emission
logic can be verified without requiring an actual GenAI spec rename to exist.
"""

import pytest

import gateway.semconv as semconv
from gateway.semconv import (
    ATTR_GEN_AI_OPERATION_NAME,
    ATTR_GEN_AI_REQUEST_MAX_TOKENS,
    ATTR_GEN_AI_REQUEST_MODEL,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_TOKEN_TYPE,
    ATTR_GEN_AI_USAGE_INPUT_TOKENS,
    ATTR_GEN_AI_USAGE_OUTPUT_TOKENS,
    VAL_GEN_AI_OPERATION_CHAT,
    VAL_GEN_AI_SYSTEM_OPENAI,
    VAL_GEN_AI_TOKEN_TYPE_INPUT,
    VAL_GEN_AI_TOKEN_TYPE_OUTPUT,
    resolve_attrs,
)


class TestAttrConstants:
    """Attribute name strings match published GenAI semantic conventions."""

    def test_system_attr_name(self):
        assert ATTR_GEN_AI_SYSTEM == "gen_ai.system"

    def test_operation_attr_name(self):
        assert ATTR_GEN_AI_OPERATION_NAME == "gen_ai.operation.name"

    def test_request_model_attr_name(self):
        assert ATTR_GEN_AI_REQUEST_MODEL == "gen_ai.request.model"

    def test_request_max_tokens_attr_name(self):
        assert ATTR_GEN_AI_REQUEST_MAX_TOKENS == "gen_ai.request.max_tokens"

    def test_usage_input_tokens_attr_name(self):
        assert ATTR_GEN_AI_USAGE_INPUT_TOKENS == "gen_ai.usage.input_tokens"

    def test_usage_output_tokens_attr_name(self):
        assert ATTR_GEN_AI_USAGE_OUTPUT_TOKENS == "gen_ai.usage.output_tokens"

    def test_token_type_attr_name(self):
        assert ATTR_GEN_AI_TOKEN_TYPE == "gen_ai.token.type"

    def test_system_value_openai(self):
        assert VAL_GEN_AI_SYSTEM_OPENAI == "openai"

    def test_operation_value_chat(self):
        assert VAL_GEN_AI_OPERATION_CHAT == "chat"

    def test_token_type_input_value(self):
        assert VAL_GEN_AI_TOKEN_TYPE_INPUT == "input"

    def test_token_type_output_value(self):
        assert VAL_GEN_AI_TOKEN_TYPE_OUTPUT == "output"


class TestResolveAttrsNoRenames:
    """With _PENDING_RENAMES empty, resolve_attrs is always a pass-through."""

    def test_passthrough_with_env_unset(self, monkeypatch):
        monkeypatch.delenv("OTEL_SEMCONV_STABILITY_OPT_IN", raising=False)
        attrs = {ATTR_GEN_AI_SYSTEM: VAL_GEN_AI_SYSTEM_OPENAI, "llm_gateway.route": "/test"}
        assert resolve_attrs(attrs) is attrs  # same object — no copy needed

    def test_passthrough_with_genai_opt_in(self, monkeypatch):
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "genai")
        attrs = {ATTR_GEN_AI_REQUEST_MODEL: "gpt-4o-mini"}
        assert resolve_attrs(attrs) is attrs

    def test_passthrough_with_genai_dup_opt_in(self, monkeypatch):
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "genai/dup")
        attrs = {ATTR_GEN_AI_REQUEST_MODEL: "gpt-4o"}
        assert resolve_attrs(attrs) is attrs

    def test_passthrough_with_unrelated_opt_in(self, monkeypatch):
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "http")
        attrs = {ATTR_GEN_AI_SYSTEM: VAL_GEN_AI_SYSTEM_OPENAI}
        assert resolve_attrs(attrs) is attrs


class TestResolveAttrsWithSyntheticRename:
    """Inject a synthetic rename to verify dual-emission logic."""

    @pytest.fixture(autouse=True)
    def inject_rename(self, monkeypatch):
        """Add a synthetic old→new rename for the duration of the test."""
        monkeypatch.setitem(semconv._PENDING_RENAMES, "gen_ai.system", "gen_ai.provider.name")

    def test_no_opt_in_preserves_old_attr(self, monkeypatch):
        """Without opt-in, old attribute name is emitted unchanged."""
        monkeypatch.delenv("OTEL_SEMCONV_STABILITY_OPT_IN", raising=False)
        attrs = {"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o-mini"}
        result = resolve_attrs(attrs)
        assert result["gen_ai.system"] == "openai"
        assert "gen_ai.provider.name" not in result

    def test_genai_dup_emits_both_attrs(self, monkeypatch):
        """genai/dup mode adds the new name alongside the old name."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "genai/dup")
        attrs = {"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o-mini"}
        result = resolve_attrs(attrs)
        assert result["gen_ai.system"] == "openai"
        assert result["gen_ai.provider.name"] == "openai"
        assert result["gen_ai.request.model"] == "gpt-4o-mini"

    def test_genai_dup_only_affects_renamed_attrs(self, monkeypatch):
        """genai/dup does not touch attributes not in _PENDING_RENAMES."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "genai/dup")
        attrs = {"gen_ai.request.model": "gpt-4o"}
        result = resolve_attrs(attrs)
        assert list(result.keys()) == ["gen_ai.request.model"]

    def test_genai_mode_replaces_old_with_new(self, monkeypatch):
        """genai mode replaces the old name with the new name."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "genai")
        attrs = {"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"}
        result = resolve_attrs(attrs)
        assert "gen_ai.system" not in result
        assert result["gen_ai.provider.name"] == "openai"
        assert result["gen_ai.request.model"] == "gpt-4o"

    def test_genai_mode_skips_absent_old_attr(self, monkeypatch):
        """genai mode is a no-op for an old attr that isn't in the input dict."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "genai")
        attrs = {"gen_ai.request.model": "gpt-4o"}
        result = resolve_attrs(attrs)
        assert "gen_ai.provider.name" not in result
        assert "gen_ai.system" not in result

    def test_original_dict_not_mutated(self, monkeypatch):
        """resolve_attrs must not mutate the input dict."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "genai/dup")
        original = {"gen_ai.system": "openai"}
        original_copy = dict(original)
        resolve_attrs(original)
        assert original == original_copy

    def test_comma_separated_opt_in_with_other_tokens(self, monkeypatch):
        """genai/dup works when combined with other opt-in tokens."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "http,genai/dup")
        attrs = {"gen_ai.system": "openai"}
        result = resolve_attrs(attrs)
        assert result["gen_ai.provider.name"] == "openai"
        assert result["gen_ai.system"] == "openai"
