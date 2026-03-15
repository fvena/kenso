"""FastMCP server — search and read documentation."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiosqlite
from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from kenso.backend import Backend
    from kenso.config import KensoConfig

__all__ = ["mcp"]

log = logging.getLogger("kenso")


# ── Lifespan ─────────────────────────────────────────────────────────


@dataclass
class AppContext:
    backend: Backend
    config: KensoConfig


@asynccontextmanager
async def app_lifespan(server):
    from kenso.backend import Backend
    from kenso.config import KensoConfig

    config = KensoConfig.from_env()
    logging.basicConfig(level=getattr(logging, config.log_level, logging.INFO))
    backend = Backend(config)
    await backend.startup()

    # Auto-init schema
    try:
        await backend.has_column("chunks", "file_path")
    except aiosqlite.OperationalError:
        await backend.init_schema()

    try:
        yield AppContext(backend=backend, config=config)
    finally:
        await backend.shutdown()


mcp = FastMCP("kenso", lifespan=app_lifespan, streamable_http_path="/mcp")


def _error(msg: str) -> str:
    """Return a JSON-encoded error response."""
    return json.dumps({"error": msg})


async def _ctx() -> AppContext:
    return mcp.get_context().request_context.lifespan_context


# ── Tools ─────────────────────────────────────────────────────────────


def _smart_preview(content: str, max_chars: int = 200) -> str:
    """Extract the most informative preview, skipping markdown structure."""
    lines = content.split("\n")
    parts = []
    chars = 0
    for line in lines:
        stripped = line.strip()
        # Skip headings, code fences, table rows, empty lines
        if (
            stripped.startswith("#")
            or stripped.startswith("```")
            or stripped.startswith("|")
            or not stripped
        ):
            continue
        parts.append(stripped)
        chars += len(stripped) + 1
        if chars >= max_chars:
            break
    result = " ".join(parts)
    if len(result) > max_chars:
        result = result[:max_chars] + "..."
    return result or content[:max_chars] + "..."


def _first_sentence(content: str, max_chars: int = 200) -> str:
    """Extract the first meaningful sentence from content."""
    preview = _smart_preview(content, max_chars)
    # Try to cut at first sentence boundary
    for sep in (". ", ".\n"):
        idx = preview.find(sep)
        if 0 < idx < max_chars:
            return preview[: idx + 1]
    return preview


def _detect_match_source(
    query: str,
    *,
    title: str,
    tags: list[str] | None,
    section_path: str,
    category: str | None,
) -> str:
    """Detect which column most likely drove the match, using simple term matching.

    Checks in weight order (title 10x, section_path 8x, tags 7x, category 5x)
    and returns the first match found. Falls back to "content".
    """
    terms = [t.lower() for t in query.split() if len(t) >= 2]
    if not terms:
        return "content"

    title_lower = title.lower()
    if any(t in title_lower for t in terms):
        return "title"

    if section_path:
        sp_lower = section_path.lower()
        if any(t in sp_lower for t in terms):
            return "section_path"

    if tags:
        tags_lower = " ".join(tags).lower()
        if any(t in tags_lower for t in terms):
            return "tags"

    if category:
        cat_lower = category.lower()
        if any(t in cat_lower for t in terms):
            return "category"

    return "content"


def _build_snippet(
    result: dict,
    query: str,
    match_source: str,
    max_chars: int = 200,
) -> str:
    """Build a snippet that reflects the column that drove the match."""
    content = result["content"]

    if match_source == "title":
        title = result["title"]
        remaining = max_chars - len(title) - 3  # " — " separator
        if remaining > 20:
            sentence = _first_sentence(content, remaining)
            return f"{title} — {sentence}"
        return title[:max_chars]

    if match_source == "tags":
        tags = result.get("tags") or []
        # Find which tags matched
        terms = [t.lower() for t in query.split() if len(t) >= 2]
        matching = [tag for tag in tags if any(t in tag.lower() for t in terms)]
        prefix = f"Tags: {', '.join(matching)}"
        remaining = max_chars - len(prefix) - 3
        if remaining > 20:
            sentence = _first_sentence(content, remaining)
            return f"{prefix} — {sentence}"
        return prefix[:max_chars]

    if match_source == "section_path":
        sp = result.get("section_path", "")
        remaining = max_chars - len(sp) - 3
        if remaining > 20:
            sentence = _first_sentence(content, remaining)
            return f"{sp} — {sentence}"
        return sp[:max_chars]

    if match_source == "category":
        cat = result.get("category", "")
        prefix = f"Category: {cat}"
        remaining = max_chars - len(prefix) - 3
        if remaining > 20:
            sentence = _first_sentence(content, remaining)
            return f"{prefix} — {sentence}"
        return prefix[:max_chars]

    # Default: content match — use existing behavior
    return _smart_preview(content, max_chars)


@mcp.tool()
async def search_docs(
    query: str,
    category: str | None = None,
    limit: int = 5,
) -> str:
    """Search documentation using keyword search (BM25).

    Args:
        query: Search query text.
        category: Optional filter by exact category name. Omit to search all categories. "all", empty string, etc. mean "no filter".
        limit: Maximum results (default 5).
    """
    ctx = await _ctx()
    cfg = ctx.config

    if not query or not query.strip():
        return _error("Empty query.")

    limit = max(1, min(cfg.search_limit_max, limit))
    preview = cfg.content_preview_chars

    results = await ctx.backend.search(query, category=category, limit=limit)
    items = []
    corrected_query = None
    for r in results:
        if r.get("corrected_query"):
            corrected_query = r["corrected_query"]
        match_source = _detect_match_source(
            query,
            title=r["title"],
            tags=r.get("tags"),
            section_path=r.get("section_path", ""),
            category=r.get("category"),
        )
        item = {
            "file_path": r["file_path"],
            "title": r["title"],
            "category": r.get("category"),
            "content_preview": _build_snippet(r, query, match_source, preview),
            "match_source": match_source,
            "score": round(float(r["score"]), 4),
        }
        if r.get("tags"):
            item["tags"] = r["tags"]
        if r.get("related_count"):
            item["related_count"] = r["related_count"]
        if r.get("highlight"):
            item["highlight"] = r["highlight"]
        items.append(item)

    log.info(
        "search: query=%r results=%d top=%s",
        query,
        len(items),
        items[0]["file_path"] if items else None,
    )

    if corrected_query:
        return json.dumps(
            {
                "corrected_query": corrected_query,
                "original_query": query,
                "results": items,
            },
            indent=2,
        )
    return json.dumps(items, indent=2)


_RRF_K = 60  # Standard RRF constant


@mcp.tool()
async def search_multi(
    queries: list[str],
    category: str | None = None,
    limit: int = 5,
) -> str:
    """Search with multiple queries and merge results using Reciprocal Rank Fusion.

    Useful for complex questions that span multiple concepts. Each query is
    executed independently and results are de-duplicated and merged.

    Args:
        queries: List of search query strings (2-5 recommended).
        category: Optional filter by exact category name. Omit to search all categories. "all", empty string, etc. mean "no filter".
        limit: Maximum results after merge (default 5).
    """
    ctx = await _ctx()
    cfg = ctx.config

    if not queries:
        return _error("No queries provided.")

    queries = [q.strip() for q in queries if q.strip()][:5]  # Cap at 5
    limit = max(1, min(cfg.search_limit_max, limit))
    preview = cfg.content_preview_chars

    # Run each query independently
    all_results: list[list[dict]] = []
    corrections: dict[str, str] = {}  # original → corrected
    for q in queries:
        results = await ctx.backend.search(q, category=category, limit=limit * 2)
        if results and results[0].get("corrected_query"):
            corrections[q] = results[0]["corrected_query"]
        all_results.append(results)

    # RRF merge: combine rankings across queries
    rrf_scores: dict[str, float] = {}
    best_result: dict[str, dict] = {}

    for results in all_results:
        for rank, r in enumerate(results, 1):
            fp = r["file_path"]
            rrf_scores[fp] = rrf_scores.get(fp, 0) + 1.0 / (_RRF_K + rank)
            if fp not in best_result or r["score"] > best_result[fp]["score"]:
                best_result[fp] = r

    # Sort by RRF score
    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    items = []
    # For multi-query, use combined terms for match detection
    combined_query = " ".join(queries)
    for fp, rrf_score in ranked[:limit]:
        r = best_result[fp]
        match_source = _detect_match_source(
            combined_query,
            title=r["title"],
            tags=r.get("tags"),
            section_path=r.get("section_path", ""),
            category=r.get("category"),
        )
        item = {
            "file_path": fp,
            "title": r["title"],
            "category": r.get("category"),
            "content_preview": _build_snippet(r, combined_query, match_source, preview),
            "match_source": match_source,
            "score": round(rrf_score, 4),
        }
        if r.get("tags"):
            item["tags"] = r["tags"]
        if r.get("related_count"):
            item["related_count"] = r["related_count"]
        items.append(item)

    log.info("search_multi: queries=%r results=%d", queries, len(items))

    if corrections:
        return json.dumps(
            {
                "corrections": corrections,
                "results": items,
            },
            indent=2,
        )
    return json.dumps(items, indent=2)


@mcp.tool()
async def get_doc(path: str, max_length: int | None = None) -> str:
    """Get full document content by file path.

    Args:
        path: Document file path.
        max_length: Optional max characters to return.
    """
    ctx = await _ctx()
    rows = await ctx.backend.get_doc(path)
    if not rows:
        return _error(f"No document found at path: {path}")

    first = rows[0]
    content = "\n\n".join(r["content"] for r in rows)
    truncated = False
    if max_length and len(content) > max_length:
        content = content[:max_length] + "..."
        truncated = True

    result = {
        "title": first["title"],
        "content": content,
        "category": first["category"],
        "audience": first["audience"],
        "tags": first["tags"],
    }
    if truncated:
        result["truncated"] = True
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_related(
    path: str,
    depth: int = 1,
    relation_type: str | None = None,
) -> str:
    """Find documents related to a given path via links.

    Args:
        path: Document file path.
        depth: How many hops to traverse (1=direct, 2=neighbors-of-neighbors).
        relation_type: Optional filter by relation type (e.g. "feeds_into", "triggers").
    """
    ctx = await _ctx()
    depth = max(1, min(depth, 3))  # Cap at 3 to prevent runaway traversal
    results = await ctx.backend.get_related(path, depth=depth, relation_type=relation_type)
    if results is None:
        return json.dumps({"message": "Links table not available.", "results": []}, indent=2)
    return json.dumps(results, indent=2)
