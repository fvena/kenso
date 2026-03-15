"""Tests for kenso.lint — retrieval quality linting."""

from __future__ import annotations

import json
import os

from kenso.lint import (
    FileResult,
    LintResult,
    Violation,
    _check_file,
    _compute_file_score,
    _rough_stem,
    format_detail,
    format_json,
    format_summary,
    lint_path,
)

# ── Helpers ─────────────────────────────────────────────────────────


def _make_cross_file_ctx(**overrides):
    """Default cross-file context for single-file checks."""
    ctx = {
        "all_paths": set(),
        "link_sources": set(),
        "link_targets": set(),
        "category_counts": {"docs": 5},
        "all_categories": ["docs"],
        "chunk_size": 4000,
        "yaml_available": True,
    }
    ctx.update(overrides)
    return ctx


def _check(rel_path: str, text: str, **ctx_overrides) -> list[Violation]:
    """Run _check_file with default cross-file context."""
    ctx = _make_cross_file_ctx(**ctx_overrides)
    # Add the file itself to all_paths unless overridden
    if "all_paths" not in ctx_overrides:
        ctx["all_paths"] = {rel_path}
    return _check_file(rel_path, text, **ctx)


# ── KS001: file-too-short ───────────────────────────────────────────


class TestKS001:
    def test_short_file_flagged(self):
        vs = _check("test.md", "tiny")
        assert any(v.rule == "KS001" for v in vs)

    def test_normal_file_not_flagged(self):
        text = "# Title\n\n" + "Content here. " * 10
        vs = _check("test.md", text)
        assert not any(v.rule == "KS001" for v in vs)


# ── KS002: broken-link ─────────────────────────────────────────────


class TestKS002:
    def test_broken_link_flagged(self):
        text = "---\nrelates_to: missing.md\n---\n# Title\n\nContent here is long enough."
        vs = _check("test.md", text, all_paths={"test.md"})
        assert any(v.rule == "KS002" and "missing.md" in v.message for v in vs)

    def test_valid_link_not_flagged(self):
        text = "---\nrelates_to: other.md\n---\n# Title\n\nContent here is long enough."
        vs = _check("test.md", text, all_paths={"test.md", "other.md"})
        assert not any(v.rule == "KS002" for v in vs)


# ── KS017: glob-in-link ────────────────────────────────────────────


class TestKS017:
    def test_glob_flagged(self):
        text = "---\nrelates_to: docs/*.md\n---\n# Title\n\nContent here is long enough."
        vs = _check("test.md", text)
        assert any(v.rule == "KS017" for v in vs)

    def test_question_mark_flagged(self):
        text = "---\nrelates_to: doc?.md\n---\n# Title\n\nContent here is long enough."
        vs = _check("test.md", text)
        assert any(v.rule == "KS017" for v in vs)


# ── KS010: tiny-section ────────────────────────────────────────────


class TestKS010:
    def test_tiny_section_flagged(self):
        text = "# Title\n\nPreamble content that is long enough for the preamble check.\n\n## Section\nTiny"
        vs = _check("test.md", text)
        assert any(v.rule == "KS010" for v in vs)

    def test_normal_section_not_flagged(self):
        text = "# Title\n\nPreamble.\n\n## Section\n\nThis section has enough content to pass the check easily."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS010" for v in vs)


# ── KS003: missing-tags ────────────────────────────────────────────


class TestKS003:
    def test_no_tags_flagged(self):
        text = "# Title\n\nContent here is long enough for the file."
        vs = _check("test.md", text)
        assert any(v.rule == "KS003" for v in vs)

    def test_with_tags_not_flagged(self):
        text = "---\ntags: api, search, index\n---\n# Title\n\nContent here is long enough."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS003" for v in vs)

    def test_empty_tags_flagged(self):
        text = "---\ntags:\n---\n# Title\n\nContent here is long enough."
        vs = _check("test.md", text)
        assert any(v.rule == "KS003" for v in vs)


# ── KS004: missing-title ───────────────────────────────────────────


class TestKS004:
    def test_no_title_flagged(self):
        text = "Just some content without any heading at all, making it long enough."
        vs = _check("test.md", text)
        assert any(v.rule == "KS004" for v in vs)

    def test_h1_title_not_flagged(self):
        text = "# My Document\n\nContent here."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS004" for v in vs)

    def test_frontmatter_title_not_flagged(self):
        text = "---\ntitle: My Document\n---\n\nContent here."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS004" for v in vs)


# ── KS005: generic-title ───────────────────────────────────────────


class TestKS005:
    def test_generic_title_flagged(self):
        text = "# Overview\n\nContent here."
        vs = _check("test.md", text)
        assert any(v.rule == "KS005" for v in vs)

    def test_single_word_title_flagged(self):
        text = "# Deployment\n\nContent here."
        vs = _check("test.md", text)
        assert any(v.rule == "KS005" for v in vs)

    def test_descriptive_title_not_flagged(self):
        text = "# CI/CD Deployment Pipeline\n\nContent here."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS005" for v in vs)


# ── KS006: no-preamble ─────────────────────────────────────────────


class TestKS006:
    def test_no_preamble_flagged(self):
        text = "# Title\n\n## Section One\n\nContent in section."
        vs = _check("test.md", text)
        assert any(v.rule == "KS006" for v in vs)

    def test_short_preamble_flagged(self):
        text = "# Title\n\nBrief.\n\n## Section One\n\nContent in section."
        vs = _check("test.md", text)
        assert any(v.rule == "KS006" for v in vs)

    def test_sufficient_preamble_not_flagged(self):
        text = "# Title\n\nThis is a detailed preamble that provides enough context about what this document covers and why it exists.\n\n## Section One\n\nContent."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS006" for v in vs)

    def test_no_h2_no_flag(self):
        """KS006 only applies when the document has H2 sections."""
        text = "# Title\n\nJust content, no H2 headings at all."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS006" for v in vs)


# ── KS007: generic-heading ─────────────────────────────────────────


class TestKS007:
    def test_generic_heading_flagged(self):
        text = "# Doc Title\n\nPreamble content that is long enough for the test.\n\n## Configuration\n\nSettings go here."
        vs = _check("test.md", text)
        assert any(v.rule == "KS007" and "Configuration" in v.message for v in vs)

    def test_single_word_heading_flagged(self):
        text = "# Doc Title\n\nPreamble content enough.\n\n## Metrics\n\nSome content here."
        vs = _check("test.md", text)
        assert any(v.rule == "KS007" for v in vs)

    def test_specific_heading_not_flagged(self):
        text = "# Doc Title\n\nPreamble.\n\n## Database Connection Pooling\n\nContent here."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS007" for v in vs)


# ── KS008: no-h2 ───────────────────────────────────────────────────


class TestKS008:
    def test_long_doc_no_h2_flagged(self):
        text = "# Title\n\n" + "Content paragraph. " * 50
        vs = _check("test.md", text)
        assert any(v.rule == "KS008" for v in vs)

    def test_short_doc_no_h2_not_flagged(self):
        text = "# Title\n\nShort content."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS008" for v in vs)

    def test_doc_with_h2_not_flagged(self):
        text = "# Title\n\n" + "Content. " * 50 + "\n\n## Section\n\nMore content."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS008" for v in vs)


# ── KS009: oversized-section ───────────────────────────────────────


class TestKS009:
    def test_oversized_section_flagged(self):
        text = "# Title\n\nPreamble.\n\n## Big Section\n\n" + "Word " * 1000
        vs = _check("test.md", text, chunk_size=200)
        assert any(v.rule == "KS009" for v in vs)

    def test_normal_section_not_flagged(self):
        text = "# Title\n\nPreamble.\n\n## Normal Section\n\nShort content here."
        vs = _check("test.md", text, chunk_size=4000)
        assert not any(v.rule == "KS009" for v in vs)


# ── KS011: few-tags ────────────────────────────────────────────────


class TestKS011:
    def test_few_tags_flagged(self):
        text = "---\ntags: api\n---\n# Title\n\nContent here."
        vs = _check("test.md", text)
        assert any(v.rule == "KS011" for v in vs)

    def test_three_tags_not_flagged(self):
        text = "---\ntags: api, search, index\n---\n# Title\n\nContent here."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS011" for v in vs)

    def test_no_tags_no_ks011(self):
        """KS011 only fires when tags exist but < 3; missing tags is KS003."""
        text = "# Title\n\nContent here."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS011" for v in vs)


# ── KS012: orphan-doc ──────────────────────────────────────────────


class TestKS012:
    def test_orphan_flagged(self):
        text = "# Title\n\nContent here is long enough."
        vs = _check("test.md", text, link_sources=set(), link_targets=set())
        assert any(v.rule == "KS012" for v in vs)

    def test_linked_doc_not_flagged(self):
        text = "# Title\n\nContent here is long enough."
        vs = _check("test.md", text, link_sources=set(), link_targets={"test.md"})
        assert not any(v.rule == "KS012" for v in vs)

    def test_doc_with_links_not_flagged(self):
        text = "---\nrelates_to: other.md\n---\n# Title\n\nContent here."
        vs = _check("test.md", text, link_sources={"test.md"}, link_targets=set())
        assert not any(v.rule == "KS012" for v in vs)


# ── KS013: redundant-tag ───────────────────────────────────────────


class TestKS013:
    def test_redundant_tag_flagged(self):
        text = "---\ntags: deployment, scaling\n---\n# Deployment Guide\n\nContent."
        vs = _check("test.md", text)
        assert any(v.rule == "KS013" and "deployment" in v.message for v in vs)

    def test_unique_tag_not_flagged(self):
        text = "---\ntags: kubernetes, docker\n---\n# Deployment Guide\n\nContent."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS013" for v in vs)


# ── KS014: inconsistent-category ───────────────────────────────────


class TestKS014:
    def test_typo_category_flagged(self):
        text = "---\ncategory: infrastucture\n---\n# Title\n\nContent."
        vs = _check(
            "test.md",
            text,
            category_counts={"infrastucture": 1, "infrastructure": 10},
            all_categories=["infrastucture", "infrastructure"],
        )
        assert any(v.rule == "KS014" for v in vs)

    def test_unique_but_no_similar_not_flagged(self):
        text = "---\ncategory: newcategory\n---\n# Title\n\nContent."
        vs = _check(
            "test.md",
            text,
            category_counts={"newcategory": 1, "infrastructure": 10},
            all_categories=["newcategory", "infrastructure"],
        )
        assert not any(v.rule == "KS014" for v in vs)


# ── KS015: weak-lead ───────────────────────────────────────────────


class TestKS015:
    def test_weak_lead_flagged(self):
        text = "# Title\n\nPreamble content.\n\n## Config\n\nThis section describes the configuration."
        vs = _check("test.md", text)
        assert any(v.rule == "KS015" for v in vs)

    def test_strong_lead_not_flagged(self):
        text = "# Title\n\nPreamble.\n\n## Config\n\nThe API accepts three parameters."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS015" for v in vs)


# ── KS016: dangling-pronoun ────────────────────────────────────────


class TestKS016:
    def test_dangling_pronoun_flagged(self):
        text = "# Title\n\nPreamble.\n\n## Setup\n\nIt requires a database connection."
        vs = _check("test.md", text)
        assert any(v.rule == "KS016" for v in vs)

    def test_no_pronoun_not_flagged(self):
        text = "# Title\n\nPreamble.\n\n## Setup\n\nThe setup requires a database."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS016" for v in vs)

    def test_pronoun_inside_word_not_flagged(self):
        """'Italian' starts with 'It' but not 'It '."""
        text = "# Title\n\nPreamble.\n\n## Food\n\nItalian cuisine is popular."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS016" for v in vs)


# ── KS018: too-many-links ──────────────────────────────────────────


class TestKS018:
    def test_too_many_links_flagged(self):
        links = ", ".join(f"doc{i}.md" for i in range(12))
        text = f"---\nrelates_to: {links}\n---\n# Title\n\nContent."
        vs = _check("test.md", text)
        assert any(v.rule == "KS018" for v in vs)

    def test_ten_links_not_flagged(self):
        links = ", ".join(f"doc{i}.md" for i in range(10))
        text = f"---\nrelates_to: {links}\n---\n# Title\n\nContent."
        vs = _check("test.md", text)
        assert not any(v.rule == "KS018" for v in vs)


# ── Score calculation ───────────────────────────────────────────────


class TestScoreCalculation:
    def test_no_violations_score_100(self):
        assert _compute_file_score([]) == 100

    def test_missing_title_deducts_18(self):
        vs = [Violation("KS004", "warning", "missing-title", "")]
        assert _compute_file_score(vs) == 82

    def test_multiple_generic_headings_capped(self):
        vs = [Violation("KS007", "warning", "generic-heading", "") for _ in range(5)]
        score = _compute_file_score(vs)
        # 1st=6, 2nd=12, 3rd+=capped at 14 total
        assert score == 86  # 100 - 14

    def test_oversized_sections_capped(self):
        vs = [Violation("KS009", "info", "oversized-section", "") for _ in range(5)]
        score = _compute_file_score(vs)
        # 5 * 2 = 10, but capped at 6
        assert score == 94

    def test_score_never_negative(self):
        # 18 + 12 + 14 + 4 + 4 = 52, plus 7 generic headings (capped 14) = 66
        # plus 12 errors at 3 = 36 → total 102 > 100, clamped to 0
        vs = (
            [
                Violation("KS004", "warning", "missing-title", ""),
                Violation("KS003", "warning", "missing-tags", ""),
                Violation("KS008", "warning", "no-h2", ""),
                Violation("KS006", "warning", "no-preamble", ""),
                Violation("KS012", "warning", "orphan-doc", ""),
            ]
            + [Violation("KS007", "warning", "generic-heading", "") for _ in range(7)]
            + [Violation("KS001", "error", "file-too-short", "") for _ in range(12)]
        )
        assert _compute_file_score(vs) == 0

    def test_info_deducts_half_point(self):
        vs = [Violation("KS016", "info", "dangling-pronoun", "")]
        assert _compute_file_score(vs) == 100  # rounds to 100 (99.5 rounds to 100)

    def test_two_info_deducts_one_point(self):
        vs = [
            Violation("KS015", "info", "weak-lead", ""),
            Violation("KS016", "info", "dangling-pronoun", ""),
        ]
        assert _compute_file_score(vs) == 99


# ── _rough_stem ─────────────────────────────────────────────────────


class TestRoughStem:
    def test_strips_ing(self):
        assert _rough_stem("deploying") == "deploy"

    def test_strips_tion(self):
        assert _rough_stem("configuration") == "configura"

    def test_strips_s(self):
        assert _rough_stem("deployments") == "deployment"

    def test_short_word_unchanged(self):
        assert _rough_stem("go") == "go"

    def test_no_suffix(self):
        assert _rough_stem("deploy") == "deploy"


# ── Integration: lint_path ──────────────────────────────────────────


class TestLintPath:
    def test_empty_directory(self, tmp_path):
        result = lint_path(str(tmp_path))
        assert result.score == 100
        assert result.files == 0
        assert result.errors == 0

    def test_nonexistent_path(self, tmp_path):
        result = lint_path(str(tmp_path / "nonexistent"))
        assert result.score == 100
        assert result.files == 0

    def test_clean_file(self, tmp_path):
        doc = tmp_path / "good.md"
        doc.write_text(
            "---\n"
            "tags: api, search, indexing\n"
            "relates_to: other.md\n"
            "---\n"
            "# API Search Integration Guide\n\n"
            "This guide explains how the API search integration works and covers "
            "all the key concepts you need to understand to use it effectively.\n\n"
            "## Query Processing Pipeline\n\n"
            "The query processor takes raw search terms and transforms them "
            "through several stages before executing the FTS5 query.\n\n"
            "## Result Ranking Algorithm\n\n"
            "Results are ranked using BM25 with configurable column weights "
            "that prioritize title matches over content matches.\n"
        )
        other = tmp_path / "other.md"
        other.write_text(
            "---\n"
            "tags: api, docs, guide\n"
            "relates_to: good.md\n"
            "---\n"
            "# Other Document Guide\n\n"
            "This document provides additional context and details about "
            "the related API functionality and its usage patterns.\n\n"
            "## Feature Overview Details\n\n"
            "The feature set includes several components working together.\n"
        )
        result = lint_path(str(tmp_path))
        assert result.files == 2
        # Both files should have high scores (few or no violations)
        assert result.score >= 80

    def test_file_with_errors(self, tmp_path):
        doc = tmp_path / "bad.md"
        doc.write_text("tiny")
        result = lint_path(str(tmp_path))
        assert result.errors > 0
        assert result.file_results[0].violations[0].rule == "KS001"

    def test_broken_link_cross_file(self, tmp_path):
        doc = tmp_path / "a.md"
        doc.write_text(
            "---\nrelates_to: nonexistent.md\n---\n# Document A Title\n\nContent long enough."
        )
        result = lint_path(str(tmp_path))
        rules = [v.rule for fr in result.file_results for v in fr.violations]
        assert "KS002" in rules

    def test_orphan_detection(self, tmp_path):
        (tmp_path / "a.md").write_text(
            "# Doc A Title Here\n\nContent that is long enough for the test."
        )
        (tmp_path / "b.md").write_text(
            "# Doc B Title Here\n\nContent that is long enough for the test."
        )
        result = lint_path(str(tmp_path))
        rules = [v.rule for fr in result.file_results for v in fr.violations]
        assert "KS012" in rules

    def test_single_file(self, tmp_path):
        doc = tmp_path / "single.md"
        doc.write_text("# Single File Document\n\nContent that is long enough for the check.")
        result = lint_path(str(doc))
        assert result.files == 1

    def test_exit_code_zero_no_errors(self, tmp_path):
        doc = tmp_path / "ok.md"
        doc.write_text(
            "---\ntags: a, b, c\n---\n# Good Document Title\n\nContent here is sufficient."
        )
        result = lint_path(str(tmp_path))
        assert result.errors == 0  # exit code would be 0

    def test_exit_code_one_with_errors(self, tmp_path):
        doc = tmp_path / "bad.md"
        doc.write_text("x")
        result = lint_path(str(tmp_path))
        assert result.errors > 0  # exit code would be 1


# ── Output formatting ──────────────────────────────────────────────


class TestFormatSummary:
    def test_no_violations(self):
        result = LintResult(score=100, files=5, errors=0, warnings=0, info=0)
        output = format_summary(result)
        assert "100/100" in output
        assert "All checks passed" in output

    def test_with_violations(self):
        fr = FileResult(
            path="test.md",
            score=80,
            violations=[
                Violation("KS003", "warning", "missing-tags", "No tags"),
                Violation("KS008", "warning", "no-h2", "No H2"),
            ],
        )
        result = LintResult(
            score=80,
            files=1,
            errors=0,
            warnings=2,
            info=0,
            file_results=[fr],
        )
        output = format_summary(result)
        assert "80/100" in output
        assert "KS003" in output
        assert "KS008" in output
        assert "─" in output
        assert "--detail" in output

    def test_impact_ordering(self):
        fr = FileResult(
            path="test.md",
            score=50,
            violations=[
                Violation("KS012", "warning", "orphan-doc", ""),
                Violation("KS003", "warning", "missing-tags", ""),
            ],
        )
        result = LintResult(score=50, files=1, errors=0, warnings=2, info=0, file_results=[fr])
        output = format_summary(result)
        lines = output.split("\n")
        # KS003 (12% impact) should appear before KS012 (3% impact)
        ks003_line = next(i for i, line in enumerate(lines) if "KS003" in line)
        ks012_line = next(i for i, line in enumerate(lines) if "KS012" in line)
        assert ks003_line < ks012_line


class TestFormatDetail:
    def test_only_shows_files_with_violations(self):
        results = LintResult(
            score=90,
            files=2,
            errors=0,
            warnings=1,
            info=0,
            file_results=[
                FileResult(path="clean.md", score=100, violations=[]),
                FileResult(
                    path="dirty.md",
                    score=80,
                    violations=[
                        Violation("KS003", "warning", "missing-tags", "No tags"),
                    ],
                ),
            ],
        )
        output = format_detail(results)
        assert "clean.md" not in output
        assert "dirty.md" in output
        assert "80/100" in output

    def test_severity_ordering(self):
        fr = FileResult(
            path="test.md",
            score=50,
            violations=[
                Violation("KS009", "info", "oversized-section", "Too big"),
                Violation("KS001", "error", "file-too-short", "Too short"),
                Violation("KS003", "warning", "missing-tags", "No tags"),
            ],
        )
        result = LintResult(score=50, files=1, errors=1, warnings=1, info=1, file_results=[fr])
        output = format_detail(result)
        lines = [line for line in output.split("\n") if line.strip().startswith("KS")]
        assert "error" in lines[0]
        assert "warning" in lines[1]
        assert "info" in lines[2]


class TestFormatJson:
    def test_valid_json(self):
        fr = FileResult(
            path="test.md",
            score=80,
            violations=[
                Violation("KS003", "warning", "missing-tags", "No tags"),
            ],
        )
        result = LintResult(score=80, files=1, errors=0, warnings=1, info=0, file_results=[fr])
        output = format_json(result)
        parsed = json.loads(output)
        assert parsed["score"] == 80
        assert parsed["files"] == 1
        assert parsed["summary"]["warnings"] == 1
        assert len(parsed["violations"]) == 1
        assert parsed["violations"][0]["file"] == "test.md"
        assert parsed["violations"][0]["issues"][0]["rule"] == "KS003"

    def test_clean_files_excluded(self):
        result = LintResult(
            score=100,
            files=1,
            errors=0,
            warnings=0,
            info=0,
            file_results=[FileResult(path="clean.md", score=100, violations=[])],
        )
        parsed = json.loads(format_json(result))
        assert parsed["violations"] == []

    def test_score_field(self):
        parsed = json.loads(
            format_json(LintResult(score=62, files=200, errors=3, warnings=147, info=89))
        )
        assert parsed["score"] == 62
        assert parsed["files"] == 200


# ── CLI integration ─────────────────────────────────────────────────


class TestCLI:
    def test_mutually_exclusive_flags(self, tmp_path):
        """--detail and --json should be mutually exclusive."""
        import subprocess

        doc = tmp_path / "test.md"
        doc.write_text("# Title\n\nContent.")
        result = subprocess.run(
            ["python3", "-m", "kenso", "lint", str(tmp_path), "--detail", "--json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_lint_subcommand_exists(self, tmp_path):
        import subprocess

        doc = tmp_path / "test.md"
        doc.write_text(
            "---\ntags: a, b, c\n---\n# Good Title Here\n\nContent that is long enough."
        )
        result = subprocess.run(
            ["python3", "-m", "kenso", "lint", str(tmp_path)],
            capture_output=True,
            text=True,
            env={**os.environ, "KENSO_LOG_LEVEL": "WARNING"},
        )
        assert "Score:" in result.stdout

    def test_json_output(self, tmp_path):
        import subprocess

        doc = tmp_path / "test.md"
        doc.write_text("# Test Document Title\n\nContent that is long enough for the check.")
        result = subprocess.run(
            ["python3", "-m", "kenso", "lint", str(tmp_path), "--json"],
            capture_output=True,
            text=True,
            env={**os.environ, "KENSO_LOG_LEVEL": "WARNING"},
        )
        parsed = json.loads(result.stdout)
        assert "score" in parsed

    def test_exit_code_zero_no_errors(self, tmp_path):
        import subprocess

        doc = tmp_path / "test.md"
        doc.write_text(
            "---\ntags: a, b, c\n---\n# Good Title Here\n\nContent that is long enough."
        )
        result = subprocess.run(
            ["python3", "-m", "kenso", "lint", str(tmp_path)],
            capture_output=True,
            text=True,
            env={**os.environ, "KENSO_LOG_LEVEL": "WARNING"},
        )
        assert result.returncode == 0

    def test_exit_code_one_with_errors(self, tmp_path):
        import subprocess

        doc = tmp_path / "test.md"
        doc.write_text("tiny")
        result = subprocess.run(
            ["python3", "-m", "kenso", "lint", str(tmp_path)],
            capture_output=True,
            text=True,
            env={**os.environ, "KENSO_LOG_LEVEL": "WARNING"},
        )
        assert result.returncode == 1
