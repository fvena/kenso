"""Tests for kenso.server — preview and error helpers."""

from __future__ import annotations

import json

from kenso.server import _error, _smart_preview

# ── _smart_preview ───────────────────────────────────────────────────


class TestSmartPreview:
    def test_plain_text(self):
        result = _smart_preview("Hello world. This is a paragraph.", 200)
        assert "Hello world" in result

    def test_skips_headings(self):
        content = "# Title\n## Section\nActual content here."
        result = _smart_preview(content, 200)
        assert "Title" not in result
        assert "Section" not in result
        assert "Actual content" in result

    def test_skips_code_fence_markers(self):
        content = "```python\ncode here\n```\nReal content."
        result = _smart_preview(content, 200)
        assert "```" not in result
        assert "Real content" in result

    def test_skips_table_rows(self):
        content = "| col1 | col2 |\n| --- | --- |\n| val1 | val2 |\nAfter table."
        result = _smart_preview(content, 200)
        assert "col1" not in result
        assert "After table" in result

    def test_empty_content_fallback(self):
        content = "# Only Heading\n\n"
        result = _smart_preview(content, 200)
        assert len(result) > 0

    def test_truncation(self):
        content = "Word " * 100
        result = _smart_preview(content, 50)
        assert len(result) <= 54  # 50 + "..."

    def test_all_structure_falls_back_to_raw(self):
        content = "# Heading\n## Sub\n```code```\n| table |"
        result = _smart_preview(content, 200)
        assert result.endswith("...")


# ── _error helper ────────────────────────────────────────────────────


class TestErrorHelper:
    def test_returns_json(self):
        result = _error("Something went wrong.")
        parsed = json.loads(result)
        assert parsed["error"] == "Something went wrong."

    def test_always_has_error_key(self):
        parsed = json.loads(_error("test"))
        assert "error" in parsed
