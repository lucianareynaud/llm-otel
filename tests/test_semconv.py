"""Tests for gateway.semconv: attribute constants and resolve_attrs() behavior.

These tests verify the OTEL_SEMCONV_STABILITY_OPT_IN dual-emission mechanism,
the contract that all gen_ai.* attribute/metric name strings are defined only
in gateway/semconv.py, and the live gen_ai.system → gen_ai.provider.name
migration.
"""

from pathlib import Path

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
    """When _PENDING_RENAMES is cleared, resolve_attrs is always a pass-through."""

    @pytest.fixture(autouse=True)
    def clear_renames(self, monkeypatch):
        """Clear _PENDING_RENAMES for the duration of these tests."""
        monkeypatch.setattr(semconv, "_PENDING_RENAMES", {})

    def test_passthrough_with_env_unset(self, monkeypatch):
        monkeypatch.delenv("OTEL_SEMCONV_STABILITY_OPT_IN", raising=False)
        attrs: dict[str, semconv.AttrValue] = {
            ATTR_GEN_AI_SYSTEM: VAL_GEN_AI_SYSTEM_OPENAI,
            "llm_gateway.route": "/test",
        }
        assert resolve_attrs(attrs) is attrs  # same object — no copy needed

    def test_passthrough_with_latest_opt_in(self, monkeypatch):
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
        attrs: dict[str, semconv.AttrValue] = {ATTR_GEN_AI_REQUEST_MODEL: "gpt-4o-mini"}
        assert resolve_attrs(attrs) is attrs

    def test_passthrough_with_latest_dup_opt_in(self, monkeypatch):
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental/dup")
        attrs: dict[str, semconv.AttrValue] = {ATTR_GEN_AI_REQUEST_MODEL: "gpt-4o"}
        assert resolve_attrs(attrs) is attrs

    def test_passthrough_with_unrelated_opt_in(self, monkeypatch):
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "http")
        attrs: dict[str, semconv.AttrValue] = {ATTR_GEN_AI_SYSTEM: VAL_GEN_AI_SYSTEM_OPENAI}
        assert resolve_attrs(attrs) is attrs


class TestResolveAttrsActiveMigration:
    """Tests for the live gen_ai.system → gen_ai.provider.name migration.

    _PENDING_RENAMES currently contains this mapping, so these tests exercise
    the real migration (not a synthetic one).
    """

    @pytest.fixture(autouse=True)
    def _ensure_rename_active(self) -> None:
        """Assert the real migration is present — fail fast if it was removed."""
        assert semconv.ATTR_GEN_AI_SYSTEM in semconv._PENDING_RENAMES, (
            "_PENDING_RENAMES no longer contains the gen_ai.system migration. "
            "Update these tests to match the current active rename."
        )

    def test_no_opt_in_emits_legacy_attr(self, monkeypatch):
        """Default (v1.36.0): gen_ai.system emitted; gen_ai.provider.name absent."""
        monkeypatch.delenv("OTEL_SEMCONV_STABILITY_OPT_IN", raising=False)
        attrs: dict[str, semconv.AttrValue] = {
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4o-mini",
        }
        result = resolve_attrs(attrs)
        assert result["gen_ai.system"] == "openai"
        assert "gen_ai.provider.name" not in result

    def test_latest_dup_emits_both_attrs(self, monkeypatch):
        """gen_ai_latest_experimental/dup: both legacy and new names present."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental/dup")
        attrs: dict[str, semconv.AttrValue] = {
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4o-mini",
        }
        result = resolve_attrs(attrs)
        assert result["gen_ai.system"] == "openai"
        assert result["gen_ai.provider.name"] == "openai"
        assert result["gen_ai.request.model"] == "gpt-4o-mini"

    def test_latest_dup_only_affects_renamed_attrs(self, monkeypatch):
        """gen_ai_latest_experimental/dup does not touch unrelated attributes."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental/dup")
        attrs: dict[str, semconv.AttrValue] = {"gen_ai.request.model": "gpt-4o"}
        result = resolve_attrs(attrs)
        assert list(result.keys()) == ["gen_ai.request.model"]

    def test_latest_replaces_legacy_with_new(self, monkeypatch):
        """gen_ai_latest_experimental: gen_ai.system → gen_ai.provider.name only."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
        attrs: dict[str, semconv.AttrValue] = {
            "gen_ai.system": "openai",
            "gen_ai.request.model": "gpt-4o",
        }
        result = resolve_attrs(attrs)
        assert "gen_ai.system" not in result
        assert result["gen_ai.provider.name"] == "openai"
        assert result["gen_ai.request.model"] == "gpt-4o"

    def test_latest_skips_absent_legacy_attr(self, monkeypatch):
        """gen_ai_latest_experimental is a no-op when gen_ai.system absent."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
        attrs: dict[str, semconv.AttrValue] = {"gen_ai.request.model": "gpt-4o"}
        result = resolve_attrs(attrs)
        assert "gen_ai.provider.name" not in result
        assert "gen_ai.system" not in result

    def test_original_dict_not_mutated(self, monkeypatch):
        """resolve_attrs must not mutate the input dict."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental/dup")
        original: dict[str, semconv.AttrValue] = {"gen_ai.system": "openai"}
        original_copy = dict(original)
        resolve_attrs(original)
        assert original == original_copy

    def test_comma_separated_opt_in_with_other_tokens(self, monkeypatch):
        """gen_ai_latest_experimental/dup works alongside unrelated opt-in tokens."""
        monkeypatch.setenv("OTEL_SEMCONV_STABILITY_OPT_IN", "http,gen_ai_latest_experimental/dup")
        attrs: dict[str, semconv.AttrValue] = {"gen_ai.system": "openai"}
        result = resolve_attrs(attrs)
        assert result["gen_ai.provider.name"] == "openai"
        assert result["gen_ai.system"] == "openai"


# ── Semconv purity: no gen_ai.* literals outside gateway/semconv.py ──────────


class TestSemconvPurity:
    """Assert that gen_ai.* string literals are centralised in gateway/semconv.py.

    These tests prevent accidental re-introduction of inline semconv strings in
    application code. They scan source files with the ``ast`` module so they
    catch strings in all syntactic positions (variable assignments, keyword
    arguments, dict keys, etc.) without relying on fragile grep patterns.

    EXEMPT files:
      - gateway/semconv.py          (the canonical definition location)
      - tests/test_semconv.py       (assertions verify the *values* of constants)
    """

    # Files in these directories are scanned for violations.
    _SCAN_PACKAGES = ("app", "gateway", "evals", "reporting")
    # Files explicitly excluded from the purity check.
    _EXEMPT_SUFFIXES = (
        "gateway/semconv.py",
        "tests/test_semconv.py",
        "tests/test_schemas.py",
    )

    @staticmethod
    def _collect_python_files(root: Path) -> list[Path]:
        files: list[Path] = []
        for pkg in TestSemconvPurity._SCAN_PACKAGES:
            pkg_dir = root / pkg
            if pkg_dir.is_dir():
                files.extend(pkg_dir.rglob("*.py"))
        return files

    def test_no_gen_ai_literals_outside_semconv(self) -> None:
        """No Python file outside gateway/semconv.py may contain 'gen_ai.' literals."""
        import ast
        from pathlib import Path

        repo_root = Path(__file__).parent.parent
        violations: list[str] = []

        for path in self._collect_python_files(repo_root):
            rel = str(path.relative_to(repo_root))
            if any(rel.endswith(exempt) for exempt in self._EXEMPT_SUFFIXES):
                continue

            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if node.value.startswith("gen_ai."):
                        violations.append(f"{rel}:{node.lineno}: literal {node.value!r}")

        assert not violations, (
            "gen_ai.* string literals found outside gateway/semconv.py.\n"
            "Move them to gateway/semconv.py as named constants:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_metric_names_centralised(self) -> None:
        """METRIC_TOKEN_USAGE and METRIC_OPERATION_DURATION must be imported, not inlined."""
        from gateway.semconv import METRIC_OPERATION_DURATION, METRIC_TOKEN_USAGE

        assert METRIC_TOKEN_USAGE == "gen_ai.client.token.usage"
        assert METRIC_OPERATION_DURATION == "gen_ai.client.operation.duration"
