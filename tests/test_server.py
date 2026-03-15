"""Tests for kenso.server — preview, error, and match-source helpers."""

from __future__ import annotations

import json

from kenso.server import (
    _build_snippet,
    _detect_match_source,
    _error,
    _smart_preview,
)

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


# ── _detect_match_source ────────────────────────────────────────────


class TestDetectMatchSource:
    def test_title_match(self):
        src = _detect_match_source(
            "deployment pipeline",
            title="CI/CD Deployment Pipeline",
            tags=None,
            section_path="",
            category="devops",
        )
        assert src == "title"

    def test_tag_match(self):
        src = _detect_match_source(
            "kubernetes",
            title="Container Orchestration",
            tags=["kubernetes", "docker"],
            section_path="",
            category="infra",
        )
        assert src == "tags"

    def test_section_path_match(self):
        src = _detect_match_source(
            "authentication",
            title="Overview",
            tags=None,
            section_path="Security > Authentication",
            category="docs",
        )
        assert src == "section_path"

    def test_category_match(self):
        src = _detect_match_source(
            "billing",
            title="Payment Processing",
            tags=None,
            section_path="",
            category="billing",
        )
        assert src == "category"

    def test_content_fallback(self):
        src = _detect_match_source(
            "elasticsearch",
            title="Search Setup",
            tags=["search"],
            section_path="Infra",
            category="docs",
        )
        assert src == "content"

    def test_title_takes_priority_over_tags(self):
        """Title (10x) should win over tags (7x) when both match."""
        src = _detect_match_source(
            "deployment",
            title="Deployment Guide",
            tags=["deployment"],
            section_path="",
            category=None,
        )
        assert src == "title"

    def test_short_query_terms_ignored(self):
        """Single-char terms should be ignored."""
        src = _detect_match_source(
            "a",
            title="A Guide",
            tags=None,
            section_path="",
            category=None,
        )
        assert src == "content"


# ── _build_snippet ──────────────────────────────────────────────────


class TestBuildSnippet:
    def _make_result(self, **overrides):
        base = {
            "title": "Test Title",
            "content": "First sentence here. Second sentence follows.",
            "tags": None,
            "section_path": "",
            "category": "docs",
        }
        base.update(overrides)
        return base

    def test_title_snippet_includes_title_and_content(self):
        r = self._make_result(title="CI/CD Deployment Pipeline")
        snippet = _build_snippet(r, "deployment", "title", 200)
        assert snippet.startswith("CI/CD Deployment Pipeline — ")
        assert "First sentence" in snippet

    def test_tag_snippet_shows_matching_tags(self):
        r = self._make_result(tags=["kubernetes", "docker", "infra"])
        snippet = _build_snippet(r, "kubernetes", "tags", 200)
        assert "Tags: kubernetes" in snippet
        assert "docker" not in snippet.split("—")[0]  # non-matching tag not in prefix

    def test_section_path_snippet(self):
        r = self._make_result(section_path="Security > Auth")
        snippet = _build_snippet(r, "auth", "section_path", 200)
        assert snippet.startswith("Security > Auth — ")

    def test_category_snippet(self):
        r = self._make_result(category="billing")
        snippet = _build_snippet(r, "billing", "category", 200)
        assert snippet.startswith("Category: billing — ")

    def test_content_match_uses_smart_preview(self):
        r = self._make_result(content="# Heading\nReal content here.")
        snippet = _build_snippet(r, "real", "content", 200)
        assert "Real content" in snippet
        assert "Heading" not in snippet

    def test_snippet_respects_max_chars(self):
        r = self._make_result(
            title="A Very Long Title That Takes Up Space",
            content="Content. " * 50,
        )
        snippet = _build_snippet(r, "long", "title", 80)
        assert len(snippet) <= 83  # 80 + "..."
