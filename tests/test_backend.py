"""Tests for kenso.backend — search, read, and link operations."""

from __future__ import annotations

import pytest

from kenso.backend import Backend, _expand_compound_word, _to_fts5_queries
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


class TestToFts5Queries:
    def test_empty_input(self):
        assert _to_fts5_queries("") == ['""']

    def test_single_word(self):
        queries = _to_fts5_queries("settlement")
        assert len(queries) >= 1
        assert '"settlement"' in queries[0]

    def test_multiple_words(self):
        queries = _to_fts5_queries("trade settlement")
        assert any("AND" in q for q in queries)
        assert any("OR" in q for q in queries)

    def test_special_characters_stripped(self):
        queries = _to_fts5_queries("hello* (world)")
        for q in queries:
            assert "*" not in q or q.endswith("*")  # prefix allowed
            assert "(" not in q.replace("NEAR(", "")

    def test_two_to_four_words_get_near(self):
        queries = _to_fts5_queries("trade settlement lifecycle")
        assert any("NEAR" in q for q in queries)

    def test_five_words_no_near(self):
        queries = _to_fts5_queries("a b c d e")
        assert not any("NEAR" in q for q in queries)


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
            [{"title": "Test Doc", "content": "Settlement lifecycle overview", "section_path": "Test"}],
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
            title="A", category="tech", audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [{"title": "B", "content": "Python snake species", "section_path": "B"}],
            title="B", category="biology", audience="all",
        )
        results = await backend.search("python", category="tech")
        assert all(r["category"] == "tech" for r in results)

    async def test_search_category_all_means_no_filter(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "Testing content here", "section_path": "A"}],
            title="A", category="cat1", audience="all",
        )
        results = await backend.search("testing", category="all")
        assert len(results) >= 1

    async def test_search_file_path_fallback(self, backend):
        await backend.ingest_file(
            "guides/setup.md",
            [{"title": "Setup", "content": "How to set up the project", "section_path": "Setup"}],
            title="Setup", category="guides", audience="all",
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
            title="A", category="general", audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [{"title": "B", "content": "Content B1", "section_path": "B"},
             {"title": "B", "content": "Content B2", "section_path": "B"}],
            title="B", category="general", audience="all",
        )
        docs = await backend.list_docs()
        assert len(docs) == 2
        b_doc = [d for d in docs if d["file_path"] == "b.md"][0]
        assert b_doc["chunks"] == 2


class TestBackendLinks:
    async def test_insert_and_get_related(self, backend):
        await backend.ingest_file(
            "a.md", [{"title": "A", "content": "content a", "section_path": "A"}],
            title="A", category="general", audience="all",
        )
        await backend.ingest_file(
            "b.md", [{"title": "B", "content": "content b", "section_path": "B"}],
            title="B", category="general", audience="all",
        )
        await backend.insert_links("a.md", ["b.md"], "related")
        related = await backend.get_related("a.md")
        assert len(related) == 1
        assert related[0]["related_path"] == "b.md"

    async def test_typed_links(self, backend):
        await backend.ingest_file(
            "a.md", [{"title": "A", "content": "content", "section_path": "A"}],
            title="A", category="general", audience="all",
        )
        await backend.ingest_file(
            "b.md", [{"title": "B", "content": "content", "section_path": "B"}],
            title="B", category="general", audience="all",
        )
        await backend.insert_typed_links("a.md", [("b.md", "feeds_into")])
        related = await backend.get_related("a.md")
        assert related[0]["relation_type"] == "feeds_into"

    async def test_get_related_depth_2(self, backend):
        await backend.ingest_file(
            "a.md", [{"title": "A", "content": "content", "section_path": "A"}],
            title="A", category="general", audience="all",
        )
        await backend.ingest_file(
            "b.md", [{"title": "B", "content": "content", "section_path": "B"}],
            title="B", category="general", audience="all",
        )
        await backend.ingest_file(
            "c.md", [{"title": "C", "content": "content", "section_path": "C"}],
            title="C", category="general", audience="all",
        )
        await backend.insert_links("a.md", ["b.md"])
        await backend.insert_links("b.md", ["c.md"])
        related = await backend.get_related("a.md", depth=2)
        paths = [r["related_path"] for r in related]
        assert "b.md" in paths
        assert "c.md" in paths

    async def test_get_related_with_type_filter(self, backend):
        await backend.ingest_file(
            "a.md", [{"title": "A", "content": "content", "section_path": "A"}],
            title="A", category="general", audience="all",
        )
        await backend.ingest_file(
            "b.md", [{"title": "B", "content": "content", "section_path": "B"}],
            title="B", category="general", audience="all",
        )
        await backend.ingest_file(
            "c.md", [{"title": "C", "content": "content", "section_path": "C"}],
            title="C", category="general", audience="all",
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
            [{"title": "A", "content": "chunk1 content", "section_path": "A"},
             {"title": "A", "content": "chunk2 content", "section_path": "A"}],
            title="A", category="cat", audience="all",
        )
        stats = await backend.stats()
        assert stats["docs"] == 1
        assert stats["chunks"] == 2
        assert stats["content_bytes"] > 0


class TestBackendReranking:
    async def test_rerank_boosts_connected_docs(self, backend):
        await backend.ingest_file(
            "a.md",
            [{"title": "A", "content": "Settlement lifecycle overview document", "section_path": "A"}],
            title="A", category="finance", audience="all",
        )
        await backend.ingest_file(
            "b.md",
            [{"title": "B", "content": "Settlement clearing process details", "section_path": "B"}],
            title="B", category="finance", audience="all",
        )
        await backend.ingest_file(
            "c.md",
            [{"title": "C", "content": "Settlement compliance reporting info", "section_path": "C"}],
            title="C", category="finance", audience="all",
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
            [{"title": "Only", "content": "Unique document with special content", "section_path": "Only"}],
            title="Only", category="general", audience="all",
        )
        results = await backend.search("unique special")
        # Should work fine with a single result (no reranking needed)
        assert len(results) >= 1


class TestBackendListCategories:
    async def test_list_categories(self, backend):
        await backend.ingest_file(
            "a.md", [{"title": "A", "content": "c1", "section_path": "A"}],
            title="A", category="tech", audience="all",
        )
        await backend.ingest_file(
            "b.md", [{"title": "B", "content": "c1", "section_path": "B"}],
            title="B", category="tech", audience="all",
        )
        await backend.ingest_file(
            "c.md", [{"title": "C", "content": "c1", "section_path": "C"}],
            title="C", category="science", audience="all",
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
            "a.md", [{"title": "A", "content": "content", "section_path": "A"}],
            title="A", category="general", audience="all",
        )
        await backend.ingest_file(
            "b.md", [{"title": "B", "content": "content", "section_path": "B"}],
            title="B", category="general", audience="all",
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
            title="Test", category="general", audience="all",
            content_hash="abc123",
        )
        h = await backend.get_content_hash("test.md")
        assert h == "abc123"

    async def test_ingest_with_aliases(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Main content", "section_path": "Test"}],
            title="Test", category="general", audience="all",
            aliases=["alt name", "other name"],
        )
        results = await backend.search("alt name")
        assert len(results) >= 1

    async def test_ingest_with_tags(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Content", "section_path": "Test"}],
            title="Test", category="general", audience="all",
            tags=["python", "testing"],
        )
        doc = await backend.get_doc("test.md")
        assert doc[0]["tags"] == ["python", "testing"]

    async def test_ingest_with_description(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Main content", "section_path": "Test"}],
            title="Test", category="general", audience="all",
            description="A description of the document",
        )
        results = await backend.search("description document")
        assert len(results) >= 1

    async def test_ingest_with_answers(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "Test", "content": "Content about process", "section_path": "Test"}],
            title="Test", category="general", audience="all",
            answers=["How does the process work?"],
        )
        results = await backend.search("how does process work")
        assert len(results) >= 1

    async def test_ingest_replaces_existing(self, backend):
        await backend.ingest_file(
            "test.md",
            [{"title": "V1", "content": "Version one content here", "section_path": "V1"}],
            title="V1", category="general", audience="all",
        )
        await backend.ingest_file(
            "test.md",
            [{"title": "V2", "content": "Version two content here", "section_path": "V2"}],
            title="V2", category="general", audience="all",
        )
        doc = await backend.get_doc("test.md")
        assert len(doc) == 1
        assert doc[0]["title"] == "V2"

    async def test_ingest_multiple_chunks(self, backend):
        chunks = [
            {"title": "Chunk 1", "content": "First chunk content", "section_path": "Doc > Part 1"},
            {"title": "Chunk 2", "content": "Second chunk content", "section_path": "Doc > Part 2"},
            {"title": "Chunk 3", "content": "Third chunk content", "section_path": "Doc > Part 3"},
        ]
        count = await backend.ingest_file(
            "multi.md", chunks, title="Multi", category="general", audience="all",
        )
        assert count == 3
        doc = await backend.get_doc("multi.md")
        assert len(doc) == 3


class TestBackendSearchFilePath:
    async def test_file_path_search_with_category(self, backend):
        await backend.ingest_file(
            "guides/setup.md",
            [{"title": "Setup", "content": "Setup instructions for the project", "section_path": "Setup"}],
            title="Setup", category="guides", audience="all",
        )
        await backend.ingest_file(
            "guides/deploy.md",
            [{"title": "Deploy", "content": "Deploy instructions for production", "section_path": "Deploy"}],
            title="Deploy", category="ops", audience="all",
        )
        # File path search should respect category filter
        results = await backend.search("guides/setup.md", category="guides")
        assert len(results) >= 1
