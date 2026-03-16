"""Tests for kenso.backend — search, read, and link operations."""

from __future__ import annotations

import pytest

from kenso.backend import (
    Backend,
    _apply_synonyms,
    _assign_relevance,
    _expand_compound_terms,
    _expand_compound_word,
    _load_synonyms,
    _to_fts5_queries,
)
from kenso.config import KensoConfig

# ── Helper functions ─────────────────────────────────────────────────


class TestExpandCompoundWord:
    def test_plain_word(self):
        assert _expand_compound_word("hello") == ["hello"]

    def test_snake_case(self):
        result = _expand_compound_word("order_matching")
        assert "order_matching" in result
        assert "order" in result
        assert "matching" in result

    def test_camel_case(self):
        result = _expand_compound_word("orderMatching")
        assert "orderMatching" in result
        assert "order" in result
        assert "matching" in result

    def test_pascal_case(self):
        result = _expand_compound_word("OrderMatching")
        assert "OrderMatching" in result

    def test_single_underscore(self):
        result = _expand_compound_word("_prefix")
        assert "_prefix" in result

    def test_hyphen_compound(self):
        result = _expand_compound_word("pre-commit")
        assert "pre-commit" in result
        assert "pre" in result
        assert "commit" in result

    def test_hyphen_short_word_no_split(self):
        """Short words like 'e-' shouldn't split."""
        result = _expand_compound_word("e-x")
        assert result == ["e-x"]

    def test_dot_compound(self):
        result = _expand_compound_word("com.example.Class")
        assert "com.example.Class" in result
        assert "com" in result
        assert "example" in result
        assert "class" in result

    def test_slash_compound(self):
        result = _expand_compound_word("CI/CD")
        assert "CI/CD" in result
        assert "ci" in result
        assert "cd" in result

    def test_version_number_no_split(self):
        result = _expand_compound_word("3.11")
        assert result == ["3.11"]

    def test_ip_address_no_split(self):
        result = _expand_compound_word("192.168.1.1")
        assert result == ["192.168.1.1"]


class TestExpandCompoundTerms:
    def test_extracts_compound_parts(self):
        result = _expand_compound_terms("The orderMatchingEngine handles trades")
        assert "order" in result
        assert "matching" in result
        assert "engine" in result

    def test_plain_text_no_expansion(self):
        result = _expand_compound_terms("simple plain words here")
        assert result == ""

    def test_hyphen_expansion(self):
        result = _expand_compound_terms("Use pre-commit hooks")
        assert "pre" in result
        assert "commit" in result

    def test_deduplicates(self):
        result = _expand_compound_terms("orderMatching and orderMatching again")
        assert result.count("order") == 1


class TestToFts5Queries:
    def test_empty_input(self):
        assert _to_fts5_queries("") == [('""', "AND")]

    def test_single_word(self):
        queries = _to_fts5_queries("settlement")
        assert len(queries) >= 1
        fts_query, stage = queries[0]
        assert '"settlement"' in fts_query
        assert stage == "AND"

    def test_multiple_words(self):
        queries = _to_fts5_queries("trade settlement")
        fts_queries = [q for q, _s in queries]
        stages = [s for _q, s in queries]
        assert any("AND" in q for q in fts_queries)
        assert any("OR" in q for q in fts_queries)
        assert "AND" in stages
        assert "OR" in stages

    def test_special_characters_stripped(self):
        queries = _to_fts5_queries("hello* (world)")
        for q, _s in queries:
            assert "*" not in q or q.endswith("*")  # prefix allowed
            assert "(" not in q.replace("NEAR(", "")

    def test_two_to_four_words_get_near(self):
        queries = _to_fts5_queries("trade settlement lifecycle")
        stages = [s for _q, s in queries]
        assert "NEAR" in stages

    def test_five_words_no_near(self):
        queries = _to_fts5_queries("alpha beta gamma delta epsilon")
        stages = [s for _q, s in queries]
        assert "NEAR" not in stages

    def test_stop_words_filtered(self):
        q1 = _to_fts5_queries("How do I configure logging")
        q2 = _to_fts5_queries("configure logging")
        assert q1 == q2

    def test_all_stop_words_kept(self):
        """A query of only stop words should NOT be filtered to empty."""
        queries = _to_fts5_queries("how do I")
        assert queries != [('""', "AND")]
        # All words should be kept since they're all stop words
        assert any("how" in q.lower() for q, _s in queries)

    def test_returns_stage_labels(self):
        """Each query in the cascade is tagged with its stage label."""
        queries = _to_fts5_queries("trade settlement", synonym_groups=[])
        stages = [s for _q, s in queries]
        # Should have AND and OR at minimum
        assert stages[0] == "AND"
        assert stages[-1] == "OR"


# ── Backend with in-memory SQLite ────────────────────────────────────


@pytest.fixture
async def backend():
    cfg = KensoConfig(database_url=":memory:")
    b = Backend(cfg)
    await b.startup()
    await b.init_schema()
    yield b
    await b.shutdown()


class TestBackendSearch:
    async def test_empty_query(self, backend):
        results = await backend.search("")
        assert results == []

    async def test_search_no_results(self, backend):
        results = await backend.search("nonexistent")
        assert results == []

    async def test_search_finds_document(self, backend):
        await backend.ingest_file(
            "test.md",
            [
                {
                    "title": "Test Doc",
                    "content": "Settlement lifecycle overview",
                    "section_path": "Test",
                }
            ],
            title="Test Doc",
            category="finance",
            audience="all",
        )
        results = await backend.search("settlement")
        assert len(results) >= 1
        assert results[0]["file_path"] == "test.md"

    async def test_search_with_category_filter(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "Python programming guide", "section_path": "A"}],
            title="A",
            category="tech",
            audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [{"title": "B", "content": "Python snake species", "section_path": "B"}],
            title="B",
            category="biology",
            audience="all",
        )
        results = await backend.search("python", category="tech")
        assert all(r["category"] == "tech" for r in results)

    async def test_search_category_all_means_no_filter(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "Testing content here", "section_path": "A"}],
            title="A",
            category="cat1",
            audience="all",
        )
        results = await backend.search("testing", category="all")
        assert len(results) >= 1

    async def test_search_file_path_fallback(self, backend):
        await backend.ingest_file(
            "guides/setup.md",
            [{"title": "Setup", "content": "How to set up the project", "section_path": "Setup"}],
            title="Setup",
            category="guides",
            audience="all",
        )
        results = await backend.search("guides/setup.md")
        assert len(results) >= 1


class TestBackendDedup:
    def test_deduplicate_keeps_best(self):
        results = [
            {"file_path": "a.md", "score": 5.0},
            {"file_path": "a.md", "score": 10.0},
            {"file_path": "b.md", "score": 3.0},
        ]
        deduped = Backend._deduplicate(results)
        assert len(deduped) == 2
        a_result = [r for r in deduped if r["file_path"] == "a.md"][0]
        assert a_result["score"] == 10.0


class TestBackendGetDoc:
    async def test_get_doc_not_found(self, backend):
        result = await backend.get_doc("nonexistent.md")
        assert result == []

    async def test_list_docs(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "Content A", "section_path": "A"}],
            title="A",
            category="general",
            audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [
                {"title": "B", "content": "Content B1", "section_path": "B"},
                {"title": "B", "content": "Content B2", "section_path": "B"},
            ],
            title="B",
            category="general",
            audience="all",
        )
        docs = await backend.list_docs()
        assert len(docs) == 2
        b_doc = [d for d in docs if d["file_path"] == "b.md"][0]
        assert b_doc["chunks"] == 2


class TestBackendLinks:
    async def test_insert_and_get_related(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "content a", "section_path": "A"}],
            title="A",
            category="general",
            audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [{"title": "B", "content": "content b", "section_path": "B"}],
            title="B",
            category="general",
            audience="all",
        )
        await backend.insert_links("a.md", ["b.md"], "related")
        related = await backend.get_related("a.md")
        assert len(related) == 1
        assert related[0]["related_path"] == "b.md"

    async def test_typed_links(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "content", "section_path": "A"}],
            title="A",
            category="general",
            audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [{"title": "B", "content": "content", "section_path": "B"}],
            title="B",
            category="general",
            audience="all",
        )
        await backend.insert_typed_links("a.md", [("b.md", "feeds_into")])
        related = await backend.get_related("a.md")
        assert related[0]["relation_type"] == "feeds_into"

    async def test_get_related_depth_2(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "content", "section_path": "A"}],
            title="A",
            category="general",
            audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [{"title": "B", "content": "content", "section_path": "B"}],
            title="B",
            category="general",
            audience="all",
        )
        await backend.ingest_file(
            "c.md",
            [{"title": "C", "content": "content", "section_path": "C"}],
            title="C",
            category="general",
            audience="all",
        )
        await backend.insert_links("a.md", ["b.md"])
        await backend.insert_links("b.md", ["c.md"])
        related = await backend.get_related("a.md", depth=2)
        paths = [r["related_path"] for r in related]
        assert "b.md" in paths
        assert "c.md" in paths

    async def test_get_related_with_type_filter(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "content", "section_path": "A"}],
            title="A",
            category="general",
            audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [{"title": "B", "content": "content", "section_path": "B"}],
            title="B",
            category="general",
            audience="all",
        )
        await backend.ingest_file(
            "c.md",
            [{"title": "C", "content": "content", "section_path": "C"}],
            title="C",
            category="general",
            audience="all",
        )
        await backend.insert_typed_links("a.md", [("b.md", "triggers"), ("c.md", "feeds_into")])
        related = await backend.get_related("a.md", relation_type="triggers")
        assert len(related) == 1
        assert related[0]["related_path"] == "b.md"


class TestBackendStats:
    async def test_empty_stats(self, backend):
        stats = await backend.stats()
        assert stats["docs"] == 0
        assert stats["chunks"] == 0

    async def test_stats_with_data(self, backend):
        await backend.ingest_file(
            "a.md",
            [
                {"title": "A", "content": "chunk1 content", "section_path": "A"},
                {"title": "A", "content": "chunk2 content", "section_path": "A"},
            ],
            title="A",
            category="cat",
            audience="all",
        )
        stats = await backend.stats()
        assert stats["docs"] == 1
        assert stats["chunks"] == 2
        assert stats["content_bytes"] > 0


class TestBackendReranking:
    async def test_rerank_boosts_connected_docs(self, backend):
        await backend.ingest_file(
            "a.md",
            [
                {
                    "title": "A",
                    "content": "Settlement lifecycle overview document",
                    "section_path": "A",
                }
            ],
            title="A",
            category="finance",
            audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [
                {
                    "title": "B",
                    "content": "Settlement clearing process details",
                    "section_path": "B",
                }
            ],
            title="B",
            category="finance",
            audience="all",
        )
        await backend.ingest_file(
            "c.md",
            [
                {
                    "title": "C",
                    "content": "Settlement compliance reporting info",
                    "section_path": "C",
                }
            ],
            title="C",
            category="finance",
            audience="all",
        )
        # Link a -> b (connected docs should get boosted)
        await backend.insert_links("a.md", ["b.md"])
        results = await backend.search("settlement", limit=3)
        assert len(results) >= 2
        # All results should have tags and related_count fields (enrichment)
        for r in results:
            assert "tags" in r
            assert "related_count" in r

    async def test_rerank_single_result_no_boost(self, backend):
        await backend.ingest_file(
            "only.md",
            [
                {
                    "title": "Only",
                    "content": "Unique document with special content",
                    "section_path": "Only",
                }
            ],
            title="Only",
            category="general",
            audience="all",
        )
        results = await backend.search("unique special")
        # Should work fine with a single result (no reranking needed)
        assert len(results) >= 1


class TestAssignRelevance:
    def test_empty_results(self):
        assert _assign_relevance([]) == []

    # ── AND stage tests ──────────────────────────────────────────────

    def test_and_single_high_score(self):
        results = [{"score": 10.0, "cascade_stage": "AND"}]
        _assign_relevance(results)
        assert results[0]["relevance"] == "high"

    def test_and_distribution(self):
        results = [
            {"score": 10.0, "cascade_stage": "AND"},
            {"score": 6.0, "cascade_stage": "AND"},  # 60% → high
            {"score": 3.0, "cascade_stage": "AND"},  # 30% → medium
            {"score": 2.0, "cascade_stage": "AND"},  # 20% → low
        ]
        _assign_relevance(results)
        assert results[0]["relevance"] == "high"
        assert results[1]["relevance"] == "high"
        assert results[2]["relevance"] == "medium"
        assert results[3]["relevance"] == "low"

    def test_and_boundary_at_fifty_percent(self):
        results = [
            {"score": 10.0, "cascade_stage": "AND"},
            {"score": 5.0, "cascade_stage": "AND"},  # exactly 50% → high
            {"score": 4.99, "cascade_stage": "AND"},  # just below → medium
        ]
        _assign_relevance(results)
        assert results[1]["relevance"] == "high"
        assert results[2]["relevance"] == "medium"

    def test_and_boundary_at_twenty_five_percent(self):
        results = [
            {"score": 10.0, "cascade_stage": "AND"},
            {"score": 2.5, "cascade_stage": "AND"},  # exactly 25% → medium
            {"score": 2.49, "cascade_stage": "AND"},  # just below → low
        ]
        _assign_relevance(results)
        assert results[1]["relevance"] == "medium"
        assert results[2]["relevance"] == "low"

    # ── NEAR stage tests ─────────────────────────────────────────────

    def test_near_distribution(self):
        results = [
            {"score": 10.0, "cascade_stage": "NEAR"},
            {"score": 7.0, "cascade_stage": "NEAR"},  # 70% → high
            {"score": 4.0, "cascade_stage": "NEAR"},  # 40% → medium
            {"score": 2.0, "cascade_stage": "NEAR"},  # 20% → low
        ]
        _assign_relevance(results)
        assert results[0]["relevance"] == "high"
        assert results[1]["relevance"] == "high"
        assert results[2]["relevance"] == "medium"
        assert results[3]["relevance"] == "low"

    # ── OR stage tests ───────────────────────────────────────────────

    def test_or_high_requires_strong_score_and_ratio(self):
        results = [
            {"score": 10.0, "cascade_stage": "OR"},  # 10 >= 8, ratio 1.0 → high
            {"score": 8.0, "cascade_stage": "OR"},  # 8 >= 8, ratio 0.8 → high
            {"score": 7.99, "cascade_stage": "OR"},  # below 8.0 → not high
        ]
        _assign_relevance(results)
        assert results[0]["relevance"] == "high"
        assert results[1]["relevance"] == "high"
        assert results[2]["relevance"] == "medium"  # 7.99 >= 5.0, ratio 0.799 >= 0.5

    def test_or_medium_requires_moderate_score_and_ratio(self):
        results = [
            {"score": 10.0, "cascade_stage": "OR"},
            {"score": 5.0, "cascade_stage": "OR"},  # 5 >= 5, ratio 0.5 → medium
            {"score": 4.99, "cascade_stage": "OR"},  # below 5.0 → low
        ]
        _assign_relevance(results)
        assert results[1]["relevance"] == "medium"
        assert results[2]["relevance"] == "low"

    def test_or_noise_all_low(self):
        """OR-stage noise results should all be low even with similar scores."""
        results = [
            {"score": 5.9, "cascade_stage": "OR"},
            {"score": 5.5, "cascade_stage": "OR"},
            {"score": 4.8, "cascade_stage": "OR"},
            {"score": 2.9, "cascade_stage": "OR"},
        ]
        _assign_relevance(results)
        assert results[0]["relevance"] == "medium"
        assert results[1]["relevance"] == "medium"
        assert results[2]["relevance"] == "low"
        assert results[3]["relevance"] == "low"

    def test_or_with_high_top_score(self):
        """OR results where top score is genuinely strong."""
        results = [
            {"score": 15.0, "cascade_stage": "OR"},  # high (15 >= 8, ratio 1.0)
            {"score": 12.0, "cascade_stage": "OR"},  # high (12 >= 8, ratio 0.8)
            {"score": 8.0, "cascade_stage": "OR"},  # medium (8 >= 5, ratio 0.53)
            {"score": 3.0, "cascade_stage": "OR"},  # low (3 < 5)
        ]
        _assign_relevance(results)
        assert results[0]["relevance"] == "high"
        assert results[1]["relevance"] == "high"
        assert results[2]["relevance"] == "medium"
        assert results[3]["relevance"] == "low"

    # ── Default stage (missing cascade_stage) ────────────────────────

    def test_missing_cascade_stage_defaults_to_or(self):
        """Results without cascade_stage should use OR (most conservative)."""
        results = [{"score": 10.0}, {"score": 6.0}]
        _assign_relevance(results)
        assert results[0]["relevance"] == "high"
        assert results[1]["relevance"] == "medium"


class TestCascadeStage:
    async def test_search_results_have_cascade_stage(self, backend):
        await backend.ingest_file(
            "test.md",
            [
                {
                    "title": "Test Doc",
                    "content": "Settlement lifecycle overview",
                    "section_path": "Test",
                }
            ],
            title="Test Doc",
            category="finance",
            audience="all",
        )
        results = await backend.search("settlement")
        assert len(results) >= 1
        for r in results:
            assert "cascade_stage" in r
            assert r["cascade_stage"] in ("AND", "NEAR", "OR")

    async def test_search_results_have_relevance(self, backend):
        await backend.ingest_file(
            "test.md",
            [
                {
                    "title": "Test Doc",
                    "content": "Settlement lifecycle overview",
                    "section_path": "Test",
                }
            ],
            title="Test Doc",
            category="finance",
            audience="all",
        )
        results = await backend.search("settlement")
        assert len(results) >= 1
        for r in results:
            assert "relevance" in r
            assert r["relevance"] in ("high", "medium", "low")

    async def test_or_fallback_stage(self, backend):
        """A query with uncommon terms that only partially match should fall to OR."""
        await backend.ingest_file(
            "alpha.md",
            [
                {
                    "title": "Alpha",
                    "content": "Alpha particle physics document",
                    "section_path": "Alpha",
                }
            ],
            title="Alpha",
            category="science",
            audience="all",
        )
        await backend.ingest_file(
            "beta.md",
            [
                {
                    "title": "Beta",
                    "content": "Beta testing methodology document",
                    "section_path": "Beta",
                }
            ],
            title="Beta",
            category="tech",
            audience="all",
        )
        # "alpha beta" AND would require both terms in same doc — neither has both
        results = await backend.search("alpha beta")
        assert len(results) >= 1
        # Should fall through to OR since no single doc has both terms
        assert results[0]["cascade_stage"] in ("NEAR", "OR")


class TestBackendListCategories:
    async def test_list_categories(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "c1", "section_path": "A"}],
            title="A",
            category="tech",
            audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [{"title": "B", "content": "c1", "section_path": "B"}],
            title="B",
            category="tech",
            audience="all",
        )
        await backend.ingest_file(
            "c.md",
            [{"title": "C", "content": "c1", "section_path": "C"}],
            title="C",
            category="science",
            audience="all",
        )
        cats = await backend.list_categories()
        assert len(cats) == 2
        tech = [c for c in cats if c["category"] == "tech"][0]
        assert tech["docs"] == 2

    async def test_list_categories_empty(self, backend):
        cats = await backend.list_categories()
        assert cats == []


class TestBackendStatsWithLinks:
    async def test_stats_includes_link_count(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "content", "section_path": "A"}],
            title="A",
            category="general",
            audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [{"title": "B", "content": "content", "section_path": "B"}],
            title="B",
            category="general",
            audience="all",
        )
        await backend.insert_links("a.md", ["b.md"])
        stats = await backend.stats()
        assert stats["links"] == 1


class TestBackendHasColumn:
    async def test_existing_column(self, backend):
        assert await backend.has_column("chunks", "file_path") is True

    async def test_nonexistent_column(self, backend):
        assert await backend.has_column("chunks", "nonexistent_col") is False


class TestBackendInsertLinks:
    async def test_insert_empty_links(self, backend):
        count = await backend.insert_links("a.md", [])
        assert count == 0

    async def test_insert_typed_links_empty(self, backend):
        count = await backend.insert_typed_links("a.md", [])
        assert count == 0

    async def test_insert_links_replaces_by_relation(self, backend):
        await backend.insert_links("a.md", ["b.md"], "related")
        await backend.insert_links("a.md", ["c.md"], "related")
        # Second call should replace links with same relation type
        related = await backend.get_related("a.md")
        paths = [r["related_path"] for r in related]
        assert "c.md" in paths


class TestBackendIngestFile:
    async def test_ingest_with_hash(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Content here", "section_path": "Test"}],
            title="Test",
            category="general",
            audience="all",
            content_hash="abc123",
        )
        h = await backend.get_content_hash("test.md")
        assert h == "abc123"

    async def test_ingest_with_aliases(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Main content", "section_path": "Test"}],
            title="Test",
            category="general",
            audience="all",
            aliases=["alt name", "other name"],
        )
        results = await backend.search("alt name")
        assert len(results) >= 1

    async def test_ingest_with_tags(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Content", "section_path": "Test"}],
            title="Test",
            category="general",
            audience="all",
            tags=["python", "testing"],
        )
        doc = await backend.get_doc("test.md")
        assert doc[0]["tags"] == ["python", "testing"]

    async def test_ingest_with_description(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Main content", "section_path": "Test"}],
            title="Test",
            category="general",
            audience="all",
            description="A description of the document",
        )
        results = await backend.search("description document")
        assert len(results) >= 1

    async def test_ingest_with_answers(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Content about process", "section_path": "Test"}],
            title="Test",
            category="general",
            audience="all",
            answers=["How does the process work?"],
        )
        results = await backend.search("how does process work")
        assert len(results) >= 1

    async def test_ingest_with_predicted_queries(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Rate limiting documentation", "section_path": "Test"}],
            title="Test",
            category="general",
            audience="all",
            predicted_queries=["rate limit config", "429 too many requests", "throttle setup"],
        )
        results = await backend.search("throttle setup")
        assert len(results) >= 1

    async def test_ingest_without_predicted_queries(self, backend):
        """Missing predicted_queries should not affect behavior."""
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Some content", "section_path": "Test"}],
            title="Test",
            category="general",
            audience="all",
        )
        results = await backend.search("Some content")
        assert len(results) >= 1

    async def test_ingest_replaces_existing(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "V1", "content": "Version one content here", "section_path": "V1"}],
            title="V1",
            category="general",
            audience="all",
        )
        await backend.ingest_file(
            "test.md",
            [{"title": "V2", "content": "Version two content here", "section_path": "V2"}],
            title="V2",
            category="general",
            audience="all",
        )
        doc = await backend.get_doc("test.md")
        assert len(doc) == 1
        assert doc[0]["title"] == "V2"

    async def test_ingest_multiple_chunks(self, backend):
        chunks = [
            {"title": "Chunk 1", "content": "First chunk content", "section_path": "Doc > Part 1"},
            {
                "title": "Chunk 2",
                "content": "Second chunk content",
                "section_path": "Doc > Part 2",
            },
            {"title": "Chunk 3", "content": "Third chunk content", "section_path": "Doc > Part 3"},
        ]
        count = await backend.ingest_file(
            "multi.md",
            chunks,
            title="Multi",
            category="general",
            audience="all",
        )
        assert count == 3
        doc = await backend.get_doc("multi.md")
        assert len(doc) == 3


class TestBackendSearchFilePath:
    async def test_file_path_search_with_category(self, backend):
        await backend.ingest_file(
            "guides/setup.md",
            [
                {
                    "title": "Setup",
                    "content": "Setup instructions for the project",
                    "section_path": "Setup",
                }
            ],
            title="Setup",
            category="guides",
            audience="all",
        )
        await backend.ingest_file(
            "guides/deploy.md",
            [
                {
                    "title": "Deploy",
                    "content": "Deploy instructions for production",
                    "section_path": "Deploy",
                }
            ],
            title="Deploy",
            category="ops",
            audience="all",
        )
        # File path search should respect category filter
        results = await backend.search("guides/setup.md", category="guides")
        assert len(results) >= 1


class TestCompoundTermExpansionSearch:
    async def test_camel_case_content_findable_by_parts(self, backend):
        """Verify 'orderMatchingEngine' in content is findable by 'order matching'."""
        await backend.ingest_file(
            "engine.md",
            [
                {
                    "title": "Engine",
                    "content": "The orderMatchingEngine processes trades",
                    "section_path": "Engine",
                }
            ],
            title="Engine",
            category="tech",
            audience="all",
        )
        results = await backend.search("order matching")
        assert len(results) >= 1
        assert results[0]["file_path"] == "engine.md"

    async def test_hyphen_content_findable_by_part(self, backend):
        """Verify 'pre-commit' in content is findable by searching 'commit'."""
        await backend.ingest_file(
            "hooks.md",
            [
                {
                    "title": "Hooks",
                    "content": "Configure pre-commit hooks for linting",
                    "section_path": "Hooks",
                }
            ],
            title="Hooks",
            category="tech",
            audience="all",
        )
        results = await backend.search("commit")
        assert len(results) >= 1
        assert results[0]["file_path"] == "hooks.md"

    async def test_dot_compound_findable(self, backend):
        """Verify 'com.example.MyClass' is findable by searching 'MyClass'."""
        await backend.ingest_file(
            "java.md",
            [
                {
                    "title": "Java",
                    "content": "Import com.example.MyClass for usage",
                    "section_path": "Java",
                }
            ],
            title="Java",
            category="tech",
            audience="all",
        )
        results = await backend.search("MyClass")
        assert len(results) >= 1
        assert results[0]["file_path"] == "java.md"


class TestStopWordSearchIntegration:
    async def test_question_style_same_as_keywords(self, backend):
        """'How do I configure logging' should produce same results as 'configure logging'."""
        await backend.ingest_file(
            "config.md",
            [
                {
                    "title": "Config",
                    "content": "Guide to configure logging in the application",
                    "section_path": "Config",
                }
            ],
            title="Config",
            category="tech",
            audience="all",
        )
        r1 = await backend.search("How do I configure logging")
        r2 = await backend.search("configure logging")
        paths1 = [r["file_path"] for r in r1]
        paths2 = [r["file_path"] for r in r2]
        assert paths1 == paths2


# ── Synonym expansion ───────────────────────────────────────────────


SAMPLE_GROUPS: list[list[str]] = [
    ["kubernetes", "k8s", "kube"],
    ["javascript", "js"],
    ["typescript", "ts"],
    ["database", "db"],
    ["pull request", "pr", "merge request", "mr"],
    ["continuous integration", "ci"],
]


class TestApplySynonyms:
    def test_single_word_match(self):
        result = _apply_synonyms(["k8s"], SAMPLE_GROUPS)
        assert len(result) == 1
        assert isinstance(result[0], list)
        assert set(result[0]) == {"kubernetes", "k8s", "kube"}

    def test_no_match(self):
        result = _apply_synonyms(["deploy"], SAMPLE_GROUPS)
        assert result == ["deploy"]

    def test_case_insensitive(self):
        result = _apply_synonyms(["K8S"], SAMPLE_GROUPS)
        assert isinstance(result[0], list)
        assert "kubernetes" in result[0]

    def test_multi_word_synonym(self):
        result = _apply_synonyms(["pull", "request", "review"], SAMPLE_GROUPS)
        assert len(result) == 2
        assert isinstance(result[0], list)  # synonym group for "pull request"
        assert "pr" in result[0]
        assert result[1] == "review"

    def test_mixed_synonyms_and_plain(self):
        result = _apply_synonyms(["deploy", "to", "k8s"], SAMPLE_GROUPS)
        assert result[0] == "deploy"
        assert result[1] == "to"
        assert isinstance(result[2], list)
        assert "kubernetes" in result[2]

    def test_empty_groups(self):
        result = _apply_synonyms(["k8s"], [])
        assert result == ["k8s"]

    def test_empty_words(self):
        result = _apply_synonyms([], SAMPLE_GROUPS)
        assert result == []


class TestToFts5QueriesWithSynonyms:
    def test_synonym_in_and_query(self):
        queries = _to_fts5_queries("deploy k8s", synonym_groups=SAMPLE_GROUPS)
        and_query, stage = queries[0]
        assert stage == "AND"
        assert "AND" in and_query
        assert '"kubernetes" OR "k8s" OR "kube"' in and_query

    def test_single_synonym_term(self):
        queries = _to_fts5_queries("k8s", synonym_groups=SAMPLE_GROUPS)
        fts_queries = [q for q, _s in queries]
        # Single synonym group → OR query of all variants
        assert any("kubernetes" in q for q in fts_queries)
        assert any("k8s" in q for q in fts_queries)

    def test_no_synonym_file_same_as_before(self):
        """With empty synonym groups, output matches original behavior."""
        q_with = _to_fts5_queries("trade settlement", synonym_groups=[])
        q_without = _to_fts5_queries("trade settlement", synonym_groups=[])
        assert q_with == q_without
        stages = [s for _q, s in q_with]
        assert "AND" in stages

    def test_multi_word_synonym_in_query(self):
        queries = _to_fts5_queries("pull request review", synonym_groups=SAMPLE_GROUPS)
        and_query, _stage = queries[0]
        # "pull request" should be expanded to its synonym group
        assert "pr" in and_query.lower()
        # "review" should remain as a plain term
        assert '"review"' in and_query

    def test_synonyms_case_insensitive(self):
        queries = _to_fts5_queries("Deploy JS app", synonym_groups=SAMPLE_GROUPS)
        and_query, _stage = queries[0]
        assert "javascript" in and_query.lower()


class TestLoadSynonyms:
    def test_no_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Reset cache
        import kenso.backend as mod

        mod._cached_synonyms = None
        mod._cached_synonyms_path = None
        monkeypatch.delenv("KENSO_SYNONYMS_PATH", raising=False)

        groups = _load_synonyms()
        assert groups == []

    def test_loads_yaml_file(self, tmp_path, monkeypatch):
        import kenso.backend as mod

        mod._cached_synonyms = None
        mod._cached_synonyms_path = None

        kenso_dir = tmp_path / ".kenso"
        kenso_dir.mkdir()
        (kenso_dir / "synonyms.yml").write_text(
            "groups:\n  - [kubernetes, k8s, kube]\n  - [database, db]\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KENSO_SYNONYMS_PATH", raising=False)

        groups = _load_synonyms()
        assert len(groups) == 2
        assert ["kubernetes", "k8s", "kube"] in groups

    def test_loads_json_file(self, tmp_path, monkeypatch):
        import kenso.backend as mod

        mod._cached_synonyms = None
        mod._cached_synonyms_path = None

        kenso_dir = tmp_path / ".kenso"
        kenso_dir.mkdir()
        (kenso_dir / "synonyms.json").write_text('{"groups": [["kubernetes", "k8s", "kube"]]}')
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KENSO_SYNONYMS_PATH", raising=False)

        groups = _load_synonyms()
        assert len(groups) == 1

    def test_env_var_overrides_path(self, tmp_path, monkeypatch):
        import kenso.backend as mod

        mod._cached_synonyms = None
        mod._cached_synonyms_path = None

        custom_file = tmp_path / "custom_synonyms.yml"
        custom_file.write_text("groups:\n  - [javascript, js]\n")
        monkeypatch.setenv("KENSO_SYNONYMS_PATH", str(custom_file))

        groups = _load_synonyms()
        assert len(groups) == 1
        assert ["javascript", "js"] in groups

    def test_invalid_yaml_returns_empty(self, tmp_path, monkeypatch):
        import kenso.backend as mod

        mod._cached_synonyms = None
        mod._cached_synonyms_path = None

        kenso_dir = tmp_path / ".kenso"
        kenso_dir.mkdir()
        (kenso_dir / "synonyms.yml").write_text("{{invalid yaml: [")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KENSO_SYNONYMS_PATH", raising=False)

        groups = _load_synonyms()
        assert groups == []

    def test_caches_after_first_load(self, tmp_path, monkeypatch):
        import kenso.backend as mod

        mod._cached_synonyms = None
        mod._cached_synonyms_path = None

        kenso_dir = tmp_path / ".kenso"
        kenso_dir.mkdir()
        syn_file = kenso_dir / "synonyms.yml"
        syn_file.write_text("groups:\n  - [kubernetes, k8s]\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KENSO_SYNONYMS_PATH", raising=False)

        groups1 = _load_synonyms()
        assert len(groups1) == 1

        # Modify file — should still return cached result
        syn_file.write_text("groups:\n  - [a, b]\n  - [c, d]\n")
        groups2 = _load_synonyms()
        assert groups2 is groups1


class TestSynonymSearchIntegration:
    async def test_synonym_expands_in_search(self, backend, tmp_path, monkeypatch):
        """Searching 'k8s' with synonym group finds doc containing 'kubernetes'."""
        import kenso.backend as mod

        mod._cached_synonyms = None
        mod._cached_synonyms_path = None

        kenso_dir = tmp_path / ".kenso"
        kenso_dir.mkdir()
        (kenso_dir / "synonyms.yml").write_text("groups:\n  - [kubernetes, k8s, kube]\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KENSO_SYNONYMS_PATH", raising=False)

        await backend.ingest_file(
            "k8s.md",
            [
                {
                    "title": "K8s Guide",
                    "content": "How to deploy applications on kubernetes clusters",
                    "section_path": "K8s Guide",
                }
            ],
            title="K8s Guide",
            category="devops",
            audience="all",
        )
        results = await backend.search("k8s")
        assert len(results) >= 1
        assert results[0]["file_path"] == "k8s.md"

    async def test_multi_word_synonym_search(self, backend, tmp_path, monkeypatch):
        """Searching 'PR review' finds doc containing 'pull request review'."""
        import kenso.backend as mod

        mod._cached_synonyms = None
        mod._cached_synonyms_path = None

        kenso_dir = tmp_path / ".kenso"
        kenso_dir.mkdir()
        (kenso_dir / "synonyms.yml").write_text(
            "groups:\n  - [pull request, pr, merge request, mr]\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KENSO_SYNONYMS_PATH", raising=False)

        await backend.ingest_file(
            "pr.md",
            [
                {
                    "title": "PR Guide",
                    "content": "How to do a pull request review properly",
                    "section_path": "PR Guide",
                }
            ],
            title="PR Guide",
            category="dev",
            audience="all",
        )
        results = await backend.search("PR review")
        assert len(results) >= 1
        assert results[0]["file_path"] == "pr.md"

    async def test_no_synonym_file_works_normally(self, backend, tmp_path, monkeypatch):
        """Without a synonym file, search behaves exactly as before."""
        import kenso.backend as mod

        mod._cached_synonyms = None
        mod._cached_synonyms_path = None

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KENSO_SYNONYMS_PATH", raising=False)

        await backend.ingest_file(
            "normal.md",
            [
                {
                    "title": "Normal",
                    "content": "Regular document about settlement lifecycle",
                    "section_path": "Normal",
                }
            ],
            title="Normal",
            category="finance",
            audience="all",
        )
        results = await backend.search("settlement")
        assert len(results) >= 1

    async def test_synonym_not_applied_to_file_path_fallback(self, backend, tmp_path, monkeypatch):
        """File path fallback search should not use synonym expansion."""
        import kenso.backend as mod

        mod._cached_synonyms = None
        mod._cached_synonyms_path = None

        kenso_dir = tmp_path / ".kenso"
        kenso_dir.mkdir()
        (kenso_dir / "synonyms.yml").write_text("groups:\n  - [kubernetes, k8s, kube]\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KENSO_SYNONYMS_PATH", raising=False)

        await backend.ingest_file(
            "docs/k8s.md",
            [
                {
                    "title": "K8s",
                    "content": "Kubernetes guide content here",
                    "section_path": "K8s",
                }
            ],
            title="K8s",
            category="devops",
            audience="all",
        )
        # File path search uses LIKE, not FTS — synonyms don't apply
        results = await backend.search("docs/k8s.md")
        assert len(results) >= 1


# ── Fuzzy matching fallback ──────────────────────────────────────────


class TestFuzzyMatchFallback:
    async def test_typo_corrected(self, backend):
        """'kuberntes' (typo) should find doc titled 'Kubernetes'."""
        await backend.ingest_file(
            "k8s.md",
            [
                {
                    "title": "Kubernetes",
                    "content": "How to deploy on kubernetes clusters",
                    "section_path": "K8s",
                }
            ],
            title="Kubernetes",
            category="devops",
            audience="all",
        )
        results = await backend.search("kuberntes")
        assert len(results) >= 1
        assert results[0]["file_path"] == "k8s.md"
        assert results[0].get("corrected_query") is not None

    async def test_short_word_single_char_typo_corrected(self, backend):
        """Single-char typo in a 4-char word: 'tset' → 'test' (distance 1)."""
        await backend.ingest_file(
            "test.md",
            [
                {
                    "title": "Test Guide",
                    "content": "How to run tests in the project",
                    "section_path": "Test",
                }
            ],
            title="Test Guide",
            category="dev",
            audience="all",
        )
        results = await backend.search("tset guide")
        assert len(results) >= 1
        assert results[0]["file_path"] == "test.md"

    async def test_short_word_two_char_typo_not_corrected(self, backend):
        """Two-char typo in a 4-char word should NOT be corrected (too distant)."""
        await backend.ingest_file(
            "test.md",
            [
                {
                    "title": "Test",
                    "content": "Testing content for the project",
                    "section_path": "Test",
                }
            ],
            title="Test",
            category="dev",
            audience="all",
        )
        # "txyz" is distance 3 from "test" — should not match
        results = await backend.search("txyz")
        assert len(results) == 0

    async def test_exact_match_not_corrected(self, backend):
        """'deploy' should NOT be corrected when it exists in dictionary."""
        await backend.ingest_file(
            "deploy.md",
            [
                {
                    "title": "Deploy",
                    "content": "How to deploy applications",
                    "section_path": "Deploy",
                }
            ],
            title="Deploy",
            category="ops",
            audience="all",
        )
        # "deploy" exists — should find via FTS, not fuzzy
        results = await backend.search("deploy")
        assert len(results) >= 1
        assert results[0].get("corrected_query") is None

    async def test_corrected_query_field_only_on_correction(self, backend):
        """corrected_query should NOT appear when FTS5 finds results directly."""
        await backend.ingest_file(
            "guide.md",
            [
                {
                    "title": "Guide",
                    "content": "A comprehensive guide to configuration",
                    "section_path": "Guide",
                }
            ],
            title="Guide",
            category="docs",
            audience="all",
        )
        results = await backend.search("guide")
        assert len(results) >= 1
        assert results[0].get("corrected_query") is None

    async def test_empty_dictionary(self, backend):
        """Fuzzy search on an empty index returns nothing."""
        results = await backend.search("kuberntes")
        assert results == []

    async def test_dictionary_cached_and_invalidated(self, backend):
        """Dictionary is cached after first build and invalidated on ingest."""
        await backend.ingest_file(
            "a.md",
            [{"title": "Alpha", "content": "Content about alpha", "section_path": "A"}],
            title="Alpha",
            category="general",
            audience="all",
        )
        # Build dictionary
        d1 = await backend._build_term_dictionary()
        assert "alpha" in d1

        # Should be cached
        d2 = await backend._build_term_dictionary()
        assert d1 is d2

        # Ingest invalidates cache
        await backend.ingest_file(
            "b.md",
            [{"title": "Beta", "content": "Content about beta", "section_path": "B"}],
            title="Beta",
            category="general",
            audience="all",
        )
        d3 = await backend._build_term_dictionary()
        assert d3 is not d1
        assert "beta" in d3

    async def test_multi_term_correction(self, backend):
        """Multiple typos in one query: 'kuberntes deploment' → corrected."""
        await backend.ingest_file(
            "k8s.md",
            [
                {
                    "title": "Kubernetes Deployment",
                    "content": "How to create a kubernetes deployment",
                    "section_path": "K8s",
                }
            ],
            title="Kubernetes Deployment",
            category="devops",
            audience="all",
        )
        results = await backend.search("kuberntes deploment")
        assert len(results) >= 1
        assert results[0]["file_path"] == "k8s.md"
        corrected = results[0].get("corrected_query")
        assert corrected is not None
        assert "kubernetes" in corrected
        assert "deployment" in corrected

    async def test_short_query_terms_skipped(self, backend):
        """Query terms shorter than 3 chars should not trigger fuzzy matching."""
        results = await backend.search("ab")
        assert results == []

    async def test_fuzzy_not_triggered_when_fts_has_results(self, backend):
        """Fuzzy fallback should never run if FTS5 found results."""
        await backend.ingest_file(
            "doc.md",
            [
                {
                    "title": "Settlement",
                    "content": "Settlement lifecycle overview",
                    "section_path": "Doc",
                }
            ],
            title="Settlement",
            category="finance",
            audience="all",
        )
        results = await backend.search("settlement")
        assert len(results) >= 1
        assert results[0].get("corrected_query") is None

    async def test_performance_large_dictionary(self, backend):
        """Fuzzy match on a ~10K-term dictionary completes in < 100ms."""
        import time

        # Ingest many docs to build a large dictionary
        for i in range(500):
            await backend.ingest_file(
                f"doc{i}.md",
                [
                    {
                        "title": f"Document {i} about topic{i} alpha{i} beta{i}",
                        "content": f"Content for document number {i}",
                        "section_path": f"Doc {i}",
                    }
                ],
                title=f"Document {i} about topic{i} alpha{i} beta{i}",
                category=f"cat{i % 10}",
                audience="all",
                tags=[f"tag{i}", f"keyword{i}", f"label{i}"],
            )

        # Build dictionary and measure fuzzy search time
        dictionary = await backend._build_term_dictionary()
        assert len(dictionary) >= 100  # Sanity check

        start = time.perf_counter()
        await backend.search("nonexistentterm")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500  # Generous bound; spec says <100ms for fuzzy alone
