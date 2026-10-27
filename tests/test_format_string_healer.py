"""
Unit, integration, and regression tests for Format String Injection & Attribute Traversal AST Healer.
"""

import pytest
from healing.format_string_healer import FormatStringHealer


class TestFormatStringHealer:
    @pytest.fixture
    def healer(self):
        return FormatStringHealer()

    # 1. Unit Tests
    def test_benign_format_string_unchanged(self, healer):
        """Benign format calls with safe placeholders should remain untouched."""
        code = "greeting = \"Hello, {name}!\".format(name=username)"
        healed, count = healer.heal_source(code)
        assert count == 0
        assert "Hello, {name}!" in healed

    def test_literal_with_dangerous_dunder_traversal_sanitized(self, healer):
        """Literal string trying to inspect object globals or class should be sanitized."""
        vulnerable = "leaked = \"Secret: {0.__class__.__init__.__globals__}\".format(obj)"
        healed, count = healer.heal_source(vulnerable)
        assert count == 1
        assert "__class__" not in healed
        assert "__globals__" not in healed
        assert "_safe_sanitized" in healed

    # 2. Integration Tests: Dynamic Template Wrapping
    def test_dynamic_user_template_wrapped(self, healer):
        """Dynamic user template variables must be wrapped in sanitizer call."""
        code = "output = user_template.format(user_data)"
        healed, count = healer.heal_source(code)
        assert count == 1
        assert "_autocure_sanitize_fmt.strip_dunder(user_template).format(user_data)" in healed

    def test_format_map_dynamic_template_wrapped(self, healer):
        """Dynamic user template using format_map must also be wrapped."""
        code = "rendered = request_template.format_map(context_dict)"
        healed, count = healer.heal_source(code)
        assert count == 1
        assert "_autocure_sanitize_fmt.strip_dunder(request_template).format_map(context_dict)" in healed

    # 3. Regression Tests: Multiple Formats in Same AST
    def test_multiple_format_invocations_healed(self, healer):
        """Multiple format invocations in functions and classes are all tracked and healed."""
        code = (
            "def render(t1, t2):\n"
            "    a = t1.format(x=1)\n"
            "    b = \"Safe {x}\".format(x=2)\n"
            "    c = t2.format(y=3)\n"
            "    return a + b + c\n"
        )
        healed, count = healer.heal_source(code)
        assert count == 2  # t1 and t2 healed, safe literal untouched
        assert len(healer.healed_locations) == 2
