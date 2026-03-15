"""Tests for kenso.ingest — parsing, chunking, and file scanning."""

from __future__ import annotations

from kenso.config import KensoConfig
from kenso.ingest import (
    _apply_overlap,
    _find_protected_ranges,
    _is_in_protected,
    _split_paragraphs_safe,
    _split_section_by_subheadings,
    chunk_by_headings,
    content_hash,
    extract_relates_to,
    extract_title,
    ingest_path,
    parse_frontmatter,
    scan_files,
)

# ── content_hash ─────────────────────────────────────────────────────


class TestContentHash:
    def test_deterministic(self):
        assert content_hash("hello") == content_hash("hello")

    def test_different_inputs(self):
        assert content_hash("hello") != content_hash("world")

    def test_length(self):
        assert len(content_hash("test")) == 16


# ── parse_frontmatter ────────────────────────────────────────────────


class TestParseFrontmatter:
    def test_no_frontmatter(self):
        meta, body = parse_frontmatter("# Hello\n\nSome content.")
        assert meta == {}
        assert body == "# Hello\n\nSome content."

    def test_simple_frontmatter(self):
        md = "---\ntitle: Test Doc\ncategory: guides\n---\n\n# Hello"
        meta, body = parse_frontmatter(md)
        assert meta["title"] == "Test Doc"
        assert meta["category"] == "guides"
        assert body.startswith("# Hello")

    def test_frontmatter_with_tags_list(self):
        md = "---\ntitle: Test\ntags:\n  - alpha\n  - beta\n---\n\nBody"
        meta, body = parse_frontmatter(md)
        assert meta["title"] == "Test"
        assert body == "Body"

    def test_unclosed_frontmatter(self):
        md = "---\ntitle: Test\nNo closing delimiter"
        meta, body = parse_frontmatter(md)
        assert meta == {}
        assert body == md

    def test_empty_frontmatter(self):
        md = "---\n---\n\nBody text"
        meta, body = parse_frontmatter(md)
        assert body == "Body text"

    def test_not_starting_with_dashes(self):
        md = "Some text\n---\ntitle: Test\n---"
        meta, body = parse_frontmatter(md)
        assert meta == {}


# ── extract_title ────────────────────────────────────────────────────


class TestExtractTitle:
    def test_h1_title(self):
        assert extract_title("# My Title\n\nContent") == "My Title"

    def test_no_h1(self):
        assert extract_title("## Subtitle\n\nContent") is None

    def test_h1_with_extra_spaces(self):
        assert extract_title("#  Spaced Title  \n\nContent") == "Spaced Title"


# ── extract_relates_to ───────────────────────────────────────────────


class TestExtractRelatesTo:
    def test_no_frontmatter(self):
        assert extract_relates_to("# Hello") == []

    def test_no_relates_to(self):
        md = "---\ntitle: Test\n---\n\nContent"
        assert extract_relates_to(md) == []

    def test_comma_separated(self):
        md = "---\nrelates_to: a.md, b.md\n---\n\nContent"
        result = extract_relates_to(md)
        paths = [r[0] for r in result]
        assert "a.md" in paths
        assert "b.md" in paths
        assert all(r[1] == "related" for r in result)

    def test_yaml_list_of_strings(self):
        md = "---\nrelates_to:\n  - a.md\n  - b.md\n---\n\nContent"
        result = extract_relates_to(md)
        paths = [r[0] for r in result]
        assert "a.md" in paths
        assert "b.md" in paths

    def test_yaml_list_of_dicts(self):
        md = (
            "---\nrelates_to:\n"
            "  - path: setup.md\n    relation: feeds_into\n"
            "  - path: overview.md\n    relation: implements\n"
            "---\n\nContent"
        )
        result = extract_relates_to(md)
        assert ("setup.md", "feeds_into") in result
        assert ("overview.md", "implements") in result

    def test_ignores_glob_patterns(self):
        md = "---\nrelates_to: *.md, docs/*.md\n---\n\nContent"
        result = extract_relates_to(md)
        assert len(result) == 0


# ── chunk_by_headings ────────────────────────────────────────────────


class TestChunkByHeadings:
    def test_no_headings(self):
        md = "Just some plain content without any headings at all."
        chunks = chunk_by_headings(md, "test.md")
        assert len(chunks) == 1
        assert chunks[0]["content"] == md

    def test_h2_splitting(self):
        md = (
            "# Doc Title\n\n"
            "Overview paragraph that is long enough to capture.\n\n"
            "## Section One\n\nContent of section one.\n\n"
            "## Section Two\n\nContent of section two."
        )
        chunks = chunk_by_headings(md, "test.md")
        titles = [c["title"] for c in chunks]
        assert any("Overview" in t for t in titles)
        assert any("Section One" in t for t in titles)
        assert any("Section Two" in t for t in titles)

    def test_preamble_too_short(self):
        md = "# Title\n\nShort.\n\n## Section\n\nContent of the section."
        chunks = chunk_by_headings(md, "test.md")
        titles = [c["title"] for c in chunks]
        assert not any("Overview" in t for t in titles)

    def test_section_path_includes_doc_title(self):
        md = "# My Doc\n\n## Features\n\nSome features described here."
        chunks = chunk_by_headings(md, "test.md")
        section_chunk = [c for c in chunks if "Features" in c["title"]][0]
        assert "My Doc" in section_chunk["section_path"]
        assert "Features" in section_chunk["section_path"]

    def test_chunk_overlap(self):
        md = (
            "# Title\n\n"
            "## Section A\n\nContent A is here with enough text to matter.\n\n"
            "## Section B\n\nContent B follows."
        )
        chunks = chunk_by_headings(md, "test.md", chunk_overlap=20)
        assert len(chunks) >= 2

    def test_uses_filename_stem_when_no_h1(self):
        md = "## Only H2\n\nSome content here."
        chunks = chunk_by_headings(md, "my-doc.md")
        assert any("my-doc" in c["title"] for c in chunks)

    def test_oversized_section_splits(self):
        long_content = "\n\n".join([f"Paragraph {i} with some text." for i in range(100)])
        md = f"# Title\n\n## Big Section\n\n{long_content}"
        chunks = chunk_by_headings(md, "test.md", max_chunk_size=500)
        assert len(chunks) > 1


# ── scan_files ───────────────────────────────────────────────────────


class TestScanFiles:
    def test_scan_directory(self, tmp_path):
        (tmp_path / "a.md").write_text("# A")
        (tmp_path / "b.md").write_text("# B")
        (tmp_path / "c.txt").write_text("not markdown")
        files = scan_files(tmp_path)
        assert len(files) == 2
        assert all(f.suffix == ".md" for f in files)

    def test_scan_single_file(self, tmp_path):
        f = tmp_path / "single.md"
        f.write_text("# Single")
        files = scan_files(f)
        assert len(files) == 1

    def test_scan_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "root.md").write_text("# Root")
        (sub / "nested.md").write_text("# Nested")
        files = scan_files(tmp_path)
        assert len(files) == 2

    def test_scan_empty_directory(self, tmp_path):
        files = scan_files(tmp_path)
        assert files == []


# ── Protected ranges ─────────────────────────────────────────────────


class TestProtectedRanges:
    def test_fenced_code_block(self):
        text = "before\n```python\ncode here\n```\nafter"
        ranges = _find_protected_ranges(text)
        assert len(ranges) >= 1
        # The code block should be protected
        code_start = text.index("```python")
        assert any(start <= code_start < end for start, end in ranges)

    def test_unclosed_code_block(self):
        text = "before\n```\ncode without closing"
        ranges = _find_protected_ranges(text)
        assert len(ranges) == 1
        assert ranges[0][1] == len(text)

    def test_table_detection(self):
        text = "before\n| A | B |\n| - | - |\n| 1 | 2 |\nafter"
        ranges = _find_protected_ranges(text)
        assert len(ranges) >= 1

    def test_table_at_end_of_text(self):
        text = "before\n| A | B |\n| 1 | 2 |"
        ranges = _find_protected_ranges(text)
        assert len(ranges) >= 1
        assert ranges[-1][1] == len(text)

    def test_no_protected_ranges(self):
        text = "Just plain text without code or tables."
        ranges = _find_protected_ranges(text)
        assert ranges == []


class TestIsInProtected:
    def test_inside_range(self):
        assert _is_in_protected(5, [(3, 10)]) is True

    def test_outside_range(self):
        assert _is_in_protected(15, [(3, 10)]) is False

    def test_at_boundary(self):
        assert _is_in_protected(3, [(3, 10)]) is True
        assert _is_in_protected(10, [(3, 10)]) is False

    def test_empty_ranges(self):
        assert _is_in_protected(5, []) is False

    def test_early_exit(self):
        assert _is_in_protected(1, [(5, 10), (15, 20)]) is False


# ── Paragraph splitting ──────────────────────────────────────────────


class TestSplitParagraphsSafe:
    def test_short_text_no_split(self):
        text = "Short text"
        result = _split_paragraphs_safe(text, 1000)
        assert result == [text]

    def test_splits_at_paragraph_boundary(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result = _split_paragraphs_safe(text, 20)
        assert len(result) >= 2

    def test_no_split_points(self):
        text = "A" * 200  # No paragraph breaks
        result = _split_paragraphs_safe(text, 50)
        assert result == [text]

    def test_does_not_split_inside_code_block(self):
        text = "Before.\n\n```\ncode\n\nmore code\n```\n\nAfter."
        result = _split_paragraphs_safe(text, 20)
        # Code block content should not be split
        for chunk in result:
            if "```" in chunk:
                # If a chunk contains opening ```, it should also contain closing
                assert chunk.count("```") == 2 or chunk.endswith("```")


# ── Sub-heading splitting ────────────────────────────────────────────


class TestSplitSectionBySubheadings:
    def test_splits_by_h3(self):
        content = (
            "## Parent\n\n"
            "### Sub One\n\nContent of sub one is here.\n\n"
            "### Sub Two\n\nContent of sub two is here."
        )
        chunks = _split_section_by_subheadings(content, "Doc", "Parent", 2, 5000)
        assert len(chunks) == 2
        assert any("Sub One" in c["title"] for c in chunks)
        assert any("Sub Two" in c["title"] for c in chunks)

    def test_no_subheadings_falls_back_to_paragraphs(self):
        content = "Long content.\n\n" * 50
        chunks = _split_section_by_subheadings(content, "Doc", "Parent", 2, 100)
        assert len(chunks) >= 2
        assert any("(cont.)" in c["title"] for c in chunks)

    def test_no_subheadings_short_content(self):
        content = "Short section content here."
        chunks = _split_section_by_subheadings(content, "Doc", "Parent", 2, 5000)
        assert len(chunks) == 1
        assert chunks[0]["title"] == "Doc > Parent"

    def test_skips_tiny_sections(self):
        content = "### Tiny\n\nX\n\n### Real\n\nThis is real content with enough text."
        chunks = _split_section_by_subheadings(content, "Doc", "Parent", 2, 5000)
        # The tiny section (< 20 chars) should be skipped
        assert all(len(c["content"]) >= 20 for c in chunks)


# ── Overlap ──────────────────────────────────────────────────────────


class TestApplyOverlap:
    def test_no_overlap(self):
        chunks = [{"title": "A", "content": "aaa"}, {"title": "B", "content": "bbb"}]
        result = _apply_overlap(chunks, 0)
        assert result[1]["content"] == "bbb"

    def test_overlap_prepends_content(self):
        chunks = [
            {"title": "A", "content": "word1 word2 word3 word4 word5"},
            {"title": "B", "content": "Content B"},
        ]
        result = _apply_overlap(chunks, 15)
        assert "Content B" in result[1]["content"]
        assert len(result[1]["content"]) > len("Content B")

    def test_overlap_skips_overview(self):
        chunks = [
            {"title": "A", "content": "word1 word2"},
            {"title": "Doc \u2014 Overview", "content": "Overview"},
        ]
        result = _apply_overlap(chunks, 10)
        assert result[1]["content"] == "Overview"

    def test_single_chunk_no_change(self):
        chunks = [{"title": "A", "content": "only one"}]
        result = _apply_overlap(chunks, 10)
        assert result == chunks

    def test_short_prev_content(self):
        chunks = [
            {"title": "A", "content": "hi"},
            {"title": "B", "content": "there"},
        ]
        result = _apply_overlap(chunks, 100)
        assert "hi" in result[1]["content"]
        assert "there" in result[1]["content"]


# ── Ingest pipeline ──────────────────────────────────────────────────


class TestIngestPath:
    async def test_nonexistent_path(self):
        cfg = KensoConfig(database_url=":memory:")
        results = await ingest_path(cfg, "/nonexistent/path")
        assert len(results) == 1
        assert results[0].action == "error"

    async def test_empty_directory(self, tmp_path):
        cfg = KensoConfig(database_url=":memory:")
        results = await ingest_path(cfg, str(tmp_path))
        assert len(results) == 1
        assert results[0].action == "skipped"

    async def test_ingest_and_reingest_unchanged(self, tmp_path):
        (tmp_path / "doc.md").write_text(
            "# My Document\n\nThis document has enough content to be indexed by kenso properly."
        )
        cfg = KensoConfig(database_url=str(tmp_path / "test.db"))
        # First ingest
        results = await ingest_path(cfg, str(tmp_path))
        assert results[0].action == "ingested"
        # Second ingest (unchanged)
        results = await ingest_path(cfg, str(tmp_path))
        assert results[0].action == "unchanged"

    async def test_ingest_with_frontmatter(self, tmp_path):
        (tmp_path / "doc.md").write_text(
            "---\ntitle: My Title\ncategory: guides\ntags:\n  - python\n  - testing\n"
            "aliases:\n  - alt name\nanswers:\n  - How to test?\n"
            "relates_to:\n  - path: other.md\n    relation: feeds_into\n---\n\n"
            "# My Title\n\nThis is a document with frontmatter metadata for testing purposes."
        )
        cfg = KensoConfig(database_url=str(tmp_path / "test.db"))
        results = await ingest_path(cfg, str(tmp_path))
        assert results[0].action == "ingested"
        assert results[0].chunks >= 1

    async def test_ingest_skips_short_content(self, tmp_path):
        (tmp_path / "tiny.md").write_text("# Short")
        cfg = KensoConfig(database_url=str(tmp_path / "test.db"))
        results = await ingest_path(cfg, str(tmp_path))
        assert results[0].action == "skipped"

    async def test_ingest_with_comma_tags(self, tmp_path):
        (tmp_path / "doc.md").write_text(
            "---\ntitle: Test\ntags: alpha, beta, gamma\n---\n\n"
            "# Test\n\nSufficient content for ingestion to happen properly in the test."
        )
        cfg = KensoConfig(database_url=str(tmp_path / "test.db"))
        results = await ingest_path(cfg, str(tmp_path))
        assert results[0].action == "ingested"


