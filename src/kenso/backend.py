"""SQLite backend — FTS5 keyword search, document read, links."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kenso.config import KensoConfig

__all__ = ["Backend"]

log = logging.getLogger("kenso")

_FTS5_SPECIAL = re.compile(r'["\*\(\)\-\+\^:]')
_CAMEL_SPLIT = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _expand_compound_word(word: str) -> list[str]:
    """Split camelCase or snake_case words into components.

    Returns the original word plus its parts, e.g.:
      "orderMatchingEngine" → ["orderMatchingEngine", "order", "matching", "engine"]
      "order_matching"      → ["order_matching", "order", "matching"]
    Plain words return as-is: ["hello"].
    """
    # snake_case
    if "_" in word:
        parts = [p for p in word.split("_") if p]
        if len(parts) > 1:
            return [word] + parts
    # camelCase / PascalCase
    parts = _CAMEL_SPLIT.split(word)
    if len(parts) > 1:
        return [word] + [p.lower() for p in parts]
    return [word]


def _to_fts5_queries(text: str) -> list[str]:
    """Build a cascade of FTS5 queries from broad to narrow.

    Strategy: AND (all terms) → NEAR (terms within 10 tokens) → OR (any term).
    Falls through to the next if insufficient results.
    """
    words = text.split()
    if not words:
        return ['""']

    # Expand camelCase / snake_case words into components
    expanded: list[str] = []
    for w in words:
        expanded.extend(_expand_compound_word(w))

    safe = []
    for w in expanded:
        cleaned = _FTS5_SPECIAL.sub("", w)
        if cleaned:
            safe.append(f'"{cleaned}"')
    if not safe:
        return ['""']
    if len(safe) == 1:
        # Single-word prefix fallback: word → [word, word*]
        cleaned = _FTS5_SPECIAL.sub("", expanded[0])
        queries = [safe[0]]
        if " " not in text and len(cleaned) >= 3:
            queries.append(f'"{cleaned}"*')
        return queries

    queries = [
        " AND ".join(safe),  # Strict: all terms must be present
    ]
    if 2 <= len(safe) <= 4:
        queries.append(f"NEAR({' '.join(safe)}, 10)")  # Proximity: terms within 10 tokens
    queries.append(" OR ".join(safe))  # Broad: any term
    return queries


class Backend:
    """SQLite backend with FTS5 search."""

    def __init__(self, config: KensoConfig) -> None:
        self._cfg = config
        self._db: Any = None
        self._db_path = config.database_url or ":memory:"

    # -- lifecycle ---------------------------------------------------------

    async def startup(self) -> None:
        import aiosqlite

        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        log.info("kenso started: path=%s", self._db_path)

    async def shutdown(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # -- schema ------------------------------------------------------------

    async def init_schema(self) -> str:
        from kenso.schema import get_schema

        statements = get_schema()
        for stmt in statements:
            await self._db.execute(stmt)
        await self._db.commit()
        return "\n".join(statements)

    # -- search ------------------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []

        log.debug("search: query=%r category=%r limit=%d", query, category, limit)

        # Sanitize category: "all", empty string, etc. mean "no filter"
        if category and category.lower() in ("all", "", "none", "*"):
            category = None

        # Fetch extra candidates for dedup + reranking headroom
        fetch_limit = limit * 3
        results = await self._search_keyword(query, category=category, limit=fetch_limit)

        # Fallback: file path LIKE search
        if not results and ("/" in query or "." in query):
            results = await self._search_file_path(query, category=category, limit=fetch_limit)

        if not results:
            return []

        # Deduplicate — keep best chunk per document
        results = self._deduplicate(results)
        log.debug("search: after dedup=%d results", len(results))

        # Fix 2.3: Re-rank by relation density within result set
        results = await self._rerank_with_relations(results)

        # Truncate to requested limit
        results = results[:limit]

        # Fix 4.4: Enrich with tags and related count
        results = await self._enrich_metadata(results)

        return results

    @staticmethod
    def _deduplicate(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep only the highest-scoring chunk per file_path."""
        seen: dict[str, dict[str, Any]] = {}
        for r in results:
            fp = r["file_path"]
            if fp not in seen or r["score"] > seen[fp]["score"]:
                seen[fp] = r
        # Preserve score-based ordering
        return sorted(seen.values(), key=lambda r: r["score"], reverse=True)

    async def _rerank_with_relations(
        self,
        results: list[dict[str, Any]],
        boost: float = 0.15,
    ) -> list[dict[str, Any]]:
        """Boost scores of results that have relates_to links between them."""
        if not await self._table_exists("links") or len(results) < 2:
            return results

        paths = [r["file_path"] for r in results]
        placeholders = ",".join("?" * len(paths))

        rows = await self._db.execute_fetchall(
            f"SELECT source_path, target_path FROM links "
            f"WHERE source_path IN ({placeholders}) AND target_path IN ({placeholders})",  # nosec B608
            paths + paths,
        )

        if not rows:
            return results

        # Count how many links each doc has within the result set
        connections: dict[str, int] = {}
        for r in rows:
            connections[r[0]] = connections.get(r[0], 0) + 1
            connections[r[1]] = connections.get(r[1], 0) + 1

        for result in results:
            fp = result["file_path"]
            if fp in connections:
                result["score"] *= 1 + boost * connections[fp]

        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    async def _enrich_metadata(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Add tags and related_count to each result (batch queries)."""
        if not results:
            return results

        paths = [r["file_path"] for r in results]
        placeholders = ",".join("?" * len(paths))

        # Batch: tags for all results in one query
        tag_rows = await self._db.execute_fetchall(
            f"SELECT file_path, tags FROM chunks "  # nosec B608
            f"WHERE file_path IN ({placeholders}) AND tags IS NOT NULL "
            f"GROUP BY file_path",
            paths,
        )
        tags_by_path: dict[str, list | None] = {}
        for row in tag_rows:
            try:
                tags_by_path[row[0]] = json.loads(row[1]) if row[1] else None
            except (json.JSONDecodeError, TypeError):
                tags_by_path[row[0]] = None

        # Batch: related counts in one query
        has_links = await self._table_exists("links")
        counts_by_path: dict[str, int] = {}
        if has_links:
            count_rows = await self._db.execute_fetchall(
                f"SELECT path, COUNT(*) FROM ("  # nosec B608
                f"  SELECT source_path AS path FROM links WHERE source_path IN ({placeholders}) "
                f"  UNION ALL "
                f"  SELECT target_path AS path FROM links WHERE target_path IN ({placeholders})"
                f") GROUP BY path",
                paths + paths,
            )
            for row in count_rows:
                counts_by_path[row[0]] = row[1]

        for r in results:
            fp = r["file_path"]
            r["tags"] = tags_by_path.get(fp)
            r["related_count"] = counts_by_path.get(fp, 0)

        return results

    async def _search_keyword(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        fts_queries = _to_fts5_queries(query)
        min_results = min(3, limit)

        for fts_query in fts_queries:
            results = await self._execute_fts(fts_query, category=category, limit=limit)
            if len(results) >= min_results:
                return results

        return results  # Return whatever the last (broadest) query found

    async def _execute_fts(
        self,
        fts_query: str,
        *,
        category: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:

        sql = (
            "SELECT c.file_path, c.title, c.content, c.category, "
            "  bm25(chunks_fts, 10.0, 8.0, 7.0, 5.0, 1.0) AS score, "
            "  snippet(chunks_fts, 4, '<mark>', '</mark>', '...', 32) AS highlight "
            "FROM chunks_fts f "
            "JOIN chunks c ON c.id = f.rowid "
            "WHERE chunks_fts MATCH ? "
        )
        params: list[Any] = [fts_query]

        if category:
            sql += "AND c.category = ? "
            params.append(category)

        sql += "ORDER BY score ASC LIMIT ?"
        params.append(limit)

        rows = await self._db.execute_fetchall(sql, params)
        return [
            {
                "file_path": r[0],
                "title": r[1],
                "content": r[2],
                "category": r[3],
                "score": -float(r[4]),
                "highlight": r[5],
            }
            for r in rows
        ]

    async def _search_file_path(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        sql = "SELECT file_path, title, content, category FROM chunks WHERE file_path LIKE ? "
        params: list[Any] = [f"%{query}%"]
        if category:
            sql += "AND category = ? "
            params.append(category)
        sql += "ORDER BY file_path, chunk_index LIMIT ?"
        params.append(limit)

        rows = await self._db.execute_fetchall(sql, params)
        return [
            {
                "file_path": r[0],
                "title": r[1],
                "content": r[2],
                "category": r[3],
                "score": 0.5,
                "highlight": None,
            }
            for r in rows
        ]

    # -- document CRUD -----------------------------------------------------

    async def get_doc(self, path: str) -> list[dict[str, Any]]:
        rows = await self._db.execute_fetchall(
            "SELECT title, content, category, audience, tags, chunk_index "
            "FROM chunks WHERE file_path = ? ORDER BY chunk_index ASC",
            (path,),
        )
        return [
            {
                "title": r[0],
                "content": r[1],
                "category": r[2],
                "audience": r[3],
                "tags": json.loads(r[4]) if r[4] else None,
                "chunk_index": r[5],
            }
            for r in rows
        ]

    async def get_related(
        self,
        path: str,
        *,
        depth: int = 1,
        relation_type: str | None = None,
    ) -> list[dict[str, Any]] | None:
        if not await self._table_exists("links"):
            return None

        traversed: set[str] = {path}  # Paths already traversed (prevent cycles)
        results: list[dict[str, Any]] = []
        seen_links: set[tuple[str, str, str]] = set()  # (related, type, direction) dedup

        async def _traverse(current: str, current_depth: int) -> None:
            if current_depth > depth:
                return

            sql = (
                "SELECT "
                "  CASE WHEN source_path = ? THEN target_path ELSE source_path END AS related, "
                "  relation_type, "
                "  CASE WHEN source_path = ? THEN 'outgoing' ELSE 'incoming' END AS direction "
                "FROM links "
                "WHERE (source_path = ? OR target_path = ?) "
            )
            params: list[Any] = [current, current, current, current]

            if relation_type:
                sql += "AND relation_type = ? "
                params.append(relation_type)

            sql += "ORDER BY relation_type, related"
            rows = await self._db.execute_fetchall(sql, params)

            next_paths: set[str] = set()
            for r in rows:
                related_path = r[0]
                link_key = (related_path, r[1], r[2])
                if link_key in seen_links:
                    continue
                seen_links.add(link_key)

                if related_path == path:
                    continue  # Skip self-references

                results.append(
                    {
                        "related_path": related_path,
                        "relation_type": r[1],
                        "direction": r[2],
                        "depth": current_depth,
                    }
                )

                if related_path not in traversed:
                    next_paths.add(related_path)

            # Traverse neighbors at next depth
            for np in next_paths:
                traversed.add(np)
                if current_depth < depth:
                    await _traverse(np, current_depth + 1)

        await _traverse(path, 1)
        return results

    async def list_docs(self) -> list[dict[str, Any]]:
        rows = await self._db.execute_fetchall(
            "SELECT file_path, MIN(title) AS title, MIN(category) AS category, "
            "  COUNT(*) AS chunks "
            "FROM chunks GROUP BY file_path ORDER BY category, file_path"
        )
        return [{"file_path": r[0], "title": r[1], "category": r[2], "chunks": r[3]} for r in rows]

    async def list_categories(self) -> list[dict[str, Any]]:
        rows = await self._db.execute_fetchall(
            "SELECT category, COUNT(DISTINCT file_path) AS docs "
            "FROM chunks WHERE category IS NOT NULL "
            "GROUP BY category ORDER BY category"
        )
        return [{"category": r[0], "docs": r[1]} for r in rows]

    # -- ingest support ----------------------------------------------------

    _ALLOWED_TABLES = {"chunks", "links", "chunks_fts"}

    async def has_column(self, table: str, column: str) -> bool:
        if table not in self._ALLOWED_TABLES:
            raise ValueError(f"Table {table!r} not in allowed list: {self._ALLOWED_TABLES}")
        rows = await self._db.execute_fetchall(f"PRAGMA table_info({table})")
        return any(r[1] == column for r in rows)

    async def get_content_hash(self, path: str) -> str | None:
        rows = await self._db.execute_fetchall(
            "SELECT content_hash FROM chunks WHERE file_path = ? LIMIT 1",
            (path,),
        )
        return rows[0][0] if rows else None

    async def insert_links(
        self,
        source_path: str,
        target_paths: list[str],
        relation_type: str = "relates_to",
    ) -> int:
        if not target_paths:
            return 0
        await self._db.execute(
            "DELETE FROM links WHERE source_path = ? AND relation_type = ?",
            (source_path, relation_type),
        )
        count = 0
        for target in target_paths:
            await self._db.execute(
                "INSERT OR IGNORE INTO links (source_path, target_path, relation_type) "
                "VALUES (?, ?, ?)",
                (source_path, target, relation_type),
            )
            count += 1
        await self._db.commit()
        return count

    async def insert_typed_links(
        self,
        source_path: str,
        links: list[tuple[str, str]],
    ) -> int:
        """Insert links with per-link relation types. Links are (target_path, relation_type)."""
        if not links:
            return 0
        # Delete all existing links from this source
        await self._db.execute("DELETE FROM links WHERE source_path = ?", (source_path,))
        count = 0
        for target, relation_type in links:
            await self._db.execute(
                "INSERT OR IGNORE INTO links (source_path, target_path, relation_type) "
                "VALUES (?, ?, ?)",
                (source_path, target, relation_type),
            )
            count += 1
        await self._db.commit()
        return count

    async def ingest_file(
        self,
        rel_path: str,
        chunks: list[dict[str, str]],
        *,
        title: str,
        category: str,
        audience: str,
        tags: list[str] | None = None,
        content_hash: str | None = None,
        aliases: list[str] | None = None,
        answers: list[str] | None = None,
        description: str | None = None,
    ) -> int:
        tags_json = json.dumps(tags) if tags else None
        await self._db.execute("DELETE FROM chunks WHERE file_path = ?", (rel_path,))
        for i, chunk in enumerate(chunks):
            # Build searchable_content: content + metadata for FTS indexing
            sc_parts = [chunk["content"]]
            if aliases:
                sc_parts.append(f"Also known as: {', '.join(aliases)}")
            if answers:
                sc_parts.append(f"Questions this document answers: {' | '.join(answers)}")
            if description:
                sc_parts.append(description)
            if tags:
                sc_parts.append(f"Keywords: {', '.join(tags)}")
            sc_parts.append(f"Source: {rel_path}")
            searchable_content = "\n\n".join(sc_parts)

            cols = "file_path, chunk_index, title, section_path, content, searchable_content, category, audience"
            vals = "?, ?, ?, ?, ?, ?, ?, ?"
            params: list[Any] = [
                rel_path,
                i,
                chunk["title"],
                chunk.get("section_path", ""),
                chunk["content"],
                searchable_content,
                category,
                audience,
            ]
            if tags_json:
                cols += ", tags"
                vals += ", ?"
                params.append(tags_json)
            if content_hash:
                cols += ", content_hash"
                vals += ", ?"
                params.append(content_hash)
            await self._db.execute(f"INSERT INTO chunks ({cols}) VALUES ({vals})", params)  # nosec B608
        await self._db.commit()
        return len(chunks)

    # -- stats -------------------------------------------------------------

    async def stats(self) -> dict[str, Any]:
        if not await self._table_exists("chunks"):
            return {
                "docs": 0,
                "chunks": 0,
                "content_bytes": 0,
                "categories": [],
                "links": None,
            }
        rows = await self._db.execute_fetchall("SELECT count(*) FROM chunks")
        total = rows[0][0]
        rows = await self._db.execute_fetchall("SELECT count(DISTINCT file_path) FROM chunks")
        docs = rows[0][0]
        cats = await self._db.execute_fetchall(
            "SELECT category, count(DISTINCT file_path), count(*) "
            "FROM chunks GROUP BY category ORDER BY 2 DESC"
        )
        rows = await self._db.execute_fetchall(
            "SELECT coalesce(sum(length(content)), 0) FROM chunks"
        )
        size = rows[0][0]
        links = None
        if await self._table_exists("links"):
            rows = await self._db.execute_fetchall("SELECT count(*) FROM links")
            links = rows[0][0]
        return {
            "docs": docs,
            "chunks": total,
            "content_bytes": size,
            "categories": [{"cat": r[0], "docs": r[1], "chunks": r[2]} for r in cats],
            "links": links,
        }

    # -- helpers -----------------------------------------------------------

    async def _table_exists(self, name: str) -> bool:
        rows = await self._db.execute_fetchall(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        )
        return len(rows) > 0
