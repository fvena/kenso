"""SQLite backend — FTS5 keyword search, document read, links."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kenso.config import KensoConfig

__all__ = [
    "Backend",
    "RELEVANCE_FLOOR_SCORE",
    "RELEVANCE_HIGH_RATIO",
    "RELEVANCE_MEDIUM_RATIO",
    "STOP_WORDS",
    "_assign_relevance",
    "_load_synonyms",
    "_apply_synonyms",
]

# ── Relevance constants ──────────────────────────────────────────────
RELEVANCE_HIGH_RATIO = 0.6
RELEVANCE_MEDIUM_RATIO = 0.3
RELEVANCE_FLOOR_SCORE = 3.0

log = logging.getLogger("kenso")

_FTS5_SPECIAL = re.compile(r'["\*\(\)\-\+\^:]')
_CAMEL_SPLIT = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_VERSION_OR_NUMBER = re.compile(r"^\d[\d.]*$")
_IP_ADDRESS = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
# Compound-word pattern: contains camelCase boundary, underscore, hyphen, dot, or slash
_COMPOUND_PATTERN = re.compile(r"[_/]|[a-z][A-Z]|[A-Z]{2}[a-z]|(?<=[a-zA-Z])[-.](?=[a-zA-Z])")

STOP_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "can",
        "may",
        "might",
        "shall",
        "how",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "it",
        "i",
        "my",
        "we",
        "our",
        "you",
        "your",
        "they",
        "their",
        "this",
        "that",
        "these",
        "those",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "from",
        "by",
        "about",
        "and",
        "or",
        "not",
        "but",
        "if",
        "so",
    }
)


def _expand_compound_word(word: str) -> list[str]:
    """Split compound words (camelCase, snake_case, hyphen, dot, slash) into components.

    Returns the original word plus its parts, e.g.:
      "orderMatchingEngine" → ["orderMatchingEngine", "order", "matching", "engine"]
      "order_matching"      → ["order_matching", "order", "matching"]
      "pre-commit"          → ["pre-commit", "pre", "commit"]
      "com.example.Class"   → ["com.example.Class", "com", "example", "class"]
    Plain words return as-is: ["hello"].
    """
    # Skip version numbers and IP addresses
    if _VERSION_OR_NUMBER.match(word) or _IP_ADDRESS.match(word):
        return [word]

    # snake_case
    if "_" in word:
        parts = [p for p in word.split("_") if p]
        if len(parts) > 1:
            return [word] + [p.lower() for p in parts]

    # Slash-separated (e.g. "CI/CD")
    if "/" in word:
        parts = [p for p in word.split("/") if p]
        if len(parts) > 1:
            return [word] + [p.lower() for p in parts]

    # Dot-separated (e.g. "com.example.Class") — but not version numbers
    if "." in word and not _VERSION_OR_NUMBER.match(word):
        parts = [p for p in word.split(".") if p]
        if len(parts) > 1:
            return [word] + [p.lower() for p in parts]

    # Hyphen-separated (e.g. "pre-commit") — skip short segments
    if "-" in word and len(word) >= 4:
        parts = [p for p in word.split("-") if p]
        if len(parts) > 1 and all(len(p) >= 2 for p in parts):
            return [word] + [p.lower() for p in parts]

    # camelCase / PascalCase
    parts = _CAMEL_SPLIT.split(word)
    if len(parts) > 1:
        return [word] + [p.lower() for p in parts]
    return [word]


def _expand_compound_terms(text: str) -> str:
    """Find compound terms in text and return space-separated expansions.

    Only expands words that contain camelCase boundaries, underscores,
    hyphens (in words ≥4 chars), dots, or slashes.
    """
    seen: set[str] = set()
    expansions: list[str] = []
    for word in text.split():
        # Strip common punctuation for matching
        clean = word.strip(".,;:!?()[]{}\"'`")
        if not clean or not _COMPOUND_PATTERN.search(clean):
            continue
        parts = _expand_compound_word(clean)
        # parts[0] is the original; parts[1:] are the components
        for p in parts[1:]:
            lower = p.lower()
            if lower not in seen:
                seen.add(lower)
                expansions.append(lower)
    return " ".join(expansions)


# -- Synonym expansion -----------------------------------------------------

_cached_synonyms: list[list[str]] | None = None
_cached_synonyms_path: str | None = None


def _load_synonyms() -> list[list[str]]:
    """Load synonym groups from .kenso/synonyms.yml or .json (cached after first load).

    Returns a list of groups, each group being a list of lowercase equivalent terms.
    """
    global _cached_synonyms, _cached_synonyms_path

    env_path = os.environ.get("KENSO_SYNONYMS_PATH")
    resolved = env_path or ".kenso/synonyms.yml"

    if _cached_synonyms is not None and _cached_synonyms_path == resolved:
        return _cached_synonyms

    _cached_synonyms_path = resolved
    _cached_synonyms = []

    p = Path(resolved)
    if not p.exists() and not env_path:
        p = Path(".kenso/synonyms.json")
    if not p.exists():
        return _cached_synonyms

    try:
        raw = p.read_text(encoding="utf-8")
        if p.suffix == ".json":
            data = json.loads(raw)
        else:
            import yaml

            data = yaml.safe_load(raw)

        if isinstance(data, dict) and "groups" in data:
            for group in data["groups"]:
                if isinstance(group, list) and len(group) >= 2:
                    _cached_synonyms.append([str(t).lower() for t in group])
    except Exception:
        log.warning("Failed to parse synonym file %s, skipping expansion", p)
        _cached_synonyms = []

    return _cached_synonyms


def _apply_synonyms(words: list[str], groups: list[list[str]]) -> list[str | list[str]]:
    """Expand query words using synonym groups.

    Returns a list where each element is either a plain word (str) or a list of
    synonym variants (list[str]) representing an OR group.  Multi-word synonym
    entries are matched against consecutive query words.
    """
    if not groups:
        return list(words)

    # Build lookup: first word of each entry → [(entry_words, group)]
    first_word_idx: dict[str, list[tuple[list[str], list[str]]]] = {}
    for group in groups:
        for entry in group:
            entry_words = entry.split()
            first = entry_words[0]
            first_word_idx.setdefault(first, []).append((entry_words, group))

    # Sort candidates longest-first so we prefer the longest match
    for candidates in first_word_idx.values():
        candidates.sort(key=lambda c: len(c[0]), reverse=True)

    result: list[str | list[str]] = []
    i = 0
    while i < len(words):
        word_lower = words[i].lower()
        matched = False

        if word_lower in first_word_idx:
            for entry_words, group in first_word_idx[word_lower]:
                n = len(entry_words)
                if i + n <= len(words):
                    query_slice = [w.lower() for w in words[i : i + n]]
                    if query_slice == entry_words:
                        result.append(group)
                        i += n
                        matched = True
                        break

        if not matched:
            result.append(words[i])
            i += 1

    return result


def _to_fts5_queries(
    text: str,
    *,
    synonym_groups: list[list[str]] | None = None,
) -> list[tuple[str, str]]:
    """Build a cascade of FTS5 queries from broad to narrow.

    Strategy: AND (all terms) → NEAR (terms within 10 tokens) → OR (any term).
    Falls through to the next if insufficient results.

    Returns a list of ``(fts_query, stage)`` tuples where *stage* is one of
    ``"AND"``, ``"NEAR"``, or ``"OR"``.

    When *synonym_groups* is ``None`` (the default), groups are loaded lazily
    from the synonym file on disk.  Pass an explicit list (even ``[]``) to
    override — useful for testing.
    """
    words = text.split()
    if not words:
        return [('""', "AND")]

    # Filter stop words (keep all if everything is a stop word)
    filtered = [w for w in words if w.lower() not in STOP_WORDS]
    if filtered:
        words = filtered

    # Synonym expansion — runs before compound-word expansion so that
    # abbreviations like "k8s" are caught on the raw query terms.
    if synonym_groups is None:
        synonym_groups = _load_synonyms()
    syn_items = _apply_synonyms(words, synonym_groups)

    # Build per-item safe tokens.  Each item is either a plain word (compound-
    # expanded) or a synonym OR group (kept as-is).
    # safe_items elements: str (single quoted token) | list[str] (OR group of quoted tokens)
    safe_items: list[str | list[str]] = []
    for item in syn_items:
        if isinstance(item, list):
            variants: list[str] = []
            for v in item:
                cleaned = _FTS5_SPECIAL.sub("", v)
                if cleaned:
                    variants.append(f'"{cleaned}"')
            if variants:
                safe_items.append(variants)
        else:
            for part in _expand_compound_word(item):
                cleaned = _FTS5_SPECIAL.sub("", part)
                if cleaned:
                    safe_items.append(f'"{cleaned}"')

    if not safe_items:
        return [('""', "AND")]

    # Flatten for counting and OR stage
    flat: list[str] = []
    for si in safe_items:
        if isinstance(si, list):
            flat.extend(si)
        else:
            flat.append(si)

    # Single-token shortcut (no synonym group)
    if len(flat) == 1 and len(safe_items) == 1 and isinstance(safe_items[0], str):
        first_raw = syn_items[0] if isinstance(syn_items[0], str) else syn_items[0][0]
        cleaned = _FTS5_SPECIAL.sub("", first_raw)
        queries: list[tuple[str, str]] = [(flat[0], "AND")]
        if " " not in text and len(cleaned) >= 3:
            queries.append((f'"{cleaned}"*', "AND"))
        return queries

    # Single synonym group only → just an OR query
    if len(safe_items) == 1 and isinstance(safe_items[0], list):
        return [(" OR ".join(safe_items[0]), "OR")]

    # -- AND stage: synonym groups become parenthesised OR sub-expressions ---
    and_parts: list[str] = []
    for si in safe_items:
        if isinstance(si, list):
            and_parts.append(f"({' OR '.join(si)})" if len(si) > 1 else si[0])
        else:
            and_parts.append(si)
    queries = [(" AND ".join(and_parts), "AND")]

    # -- NEAR stage: use first variant of each synonym group ----------------
    near_parts: list[str] = []
    for si in safe_items:
        near_parts.append(si[0] if isinstance(si, list) else si)
    if 2 <= len(near_parts) <= 4:
        queries.append((f"NEAR({' '.join(near_parts)}, 10)", "NEAR"))

    # -- OR stage: flat list of every variant --------------------------------
    queries.append((" OR ".join(flat), "OR"))

    return queries


def _assign_relevance(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tag each result with a ``relevance`` hint based on score distribution.

    - ``"high"``: score >= 60% of the best score
    - ``"medium"``: score >= 30% of the best score
    - ``"low"``: score < 30% of the best score, or all scores below floor
    """
    if not results:
        return results

    best_score = results[0]["score"]

    for r in results:
        if best_score < RELEVANCE_FLOOR_SCORE:
            r["relevance"] = "low"
        elif best_score > 0:
            ratio = r["score"] / best_score
            if ratio >= RELEVANCE_HIGH_RATIO:
                r["relevance"] = "high"
            elif ratio >= RELEVANCE_MEDIUM_RATIO:
                r["relevance"] = "medium"
            else:
                r["relevance"] = "low"
        else:
            r["relevance"] = "low"

    return results


class Backend:
    """SQLite backend with FTS5 search."""

    def __init__(self, config: KensoConfig) -> None:
        self._cfg = config
        self._db: Any = None
        self._db_path = config.database_url or ":memory:"
        self._term_dict: list[str] | None = None  # Cached fuzzy-match dictionary

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

        # Fallback: fuzzy matching on typos
        corrected_query = None
        if not results and any(len(t) >= 3 for t in query.split()):
            corrected_query, results = await self._fuzzy_search(
                query,
                category=category,
                limit=fetch_limit,
            )

        if not results:
            return []

        # Deduplicate — keep best chunk per document
        results = self._deduplicate(results)
        log.debug("search: after dedup=%d results", len(results))

        # Fix 2.3: Re-rank by relation density within result set
        results = await self._rerank_with_relations(results)

        # Truncate to requested limit
        results = results[:limit]

        # Assign relevance hints based on score distribution
        results = _assign_relevance(results)

        # Fix 4.4: Enrich with tags and related count
        results = await self._enrich_metadata(results)

        if corrected_query:
            for r in results:
                r["corrected_query"] = corrected_query

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

        results: list[dict[str, Any]] = []
        stage = "OR"  # default fallback
        for fts_query, query_stage in fts_queries:
            results = await self._execute_fts(fts_query, category=category, limit=limit)
            stage = query_stage
            if len(results) >= min_results:
                break

        for r in results:
            r["cascade_stage"] = stage

        return results

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
            "  snippet(chunks_fts, 4, '<mark>', '</mark>', '...', 32) AS highlight, "
            "  c.section_path "
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
                "section_path": r[6] or "",
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
        sql = "SELECT file_path, title, content, category, section_path FROM chunks WHERE file_path LIKE ? "
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
                "section_path": r[4] or "",
            }
            for r in rows
        ]

    # -- fuzzy matching fallback -------------------------------------------

    _MAX_DICT_SIZE = 50_000

    async def _build_term_dictionary(self) -> list[str]:
        """Extract unique lowercase terms from titles, tags, and categories."""
        if self._term_dict is not None:
            return self._term_dict

        rows = await self._db.execute_fetchall("SELECT DISTINCT title, tags, category FROM chunks")
        terms: set[str] = set()
        for row in rows:
            for col_idx in range(3):
                val = row[col_idx]
                if not val:
                    continue
                # tags column is JSON array
                if col_idx == 1:
                    try:
                        tag_list = json.loads(val)
                        for tag in tag_list:
                            for word in tag.lower().split():
                                if len(word) >= 2:
                                    terms.add(word)
                    except (json.JSONDecodeError, TypeError):
                        pass
                else:
                    for word in val.lower().split():
                        word = _FTS5_SPECIAL.sub("", word).strip()
                        if len(word) >= 2:
                            terms.add(word)

        self._term_dict = sorted(terms)
        return self._term_dict

    def _invalidate_term_dictionary(self) -> None:
        self._term_dict = None

    async def _fuzzy_search(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = 5,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Try to correct typos in query terms and re-run FTS5 search.

        Returns (corrected_query, results) or (None, []) if no correction found.
        """
        import difflib

        dictionary = await self._build_term_dictionary()
        if not dictionary or len(dictionary) > self._MAX_DICT_SIZE:
            if len(dictionary) > self._MAX_DICT_SIZE:
                log.warning("fuzzy: dictionary too large (%d terms), skipping", len(dictionary))
            return None, []

        terms = query.lower().split()
        corrected = list(terms)
        any_corrected = False

        for i, term in enumerate(terms):
            if len(term) < 3:
                continue
            # Skip if the term already exists in dictionary
            if term in dictionary:
                continue
            # Distance threshold: ≤1 for short terms (<6 chars), ≤2 for longer
            cutoff = 0.8 if len(term) >= 6 else 0.75
            # get_close_matches uses SequenceMatcher ratio, not Levenshtein directly.
            # Ratio ≥ 0.75 for 4-char word ≈ distance ≤ 1; ≥ 0.8 for 6+ ≈ distance ≤ 2
            matches = difflib.get_close_matches(term, dictionary, n=1, cutoff=cutoff)
            if matches:
                corrected[i] = matches[0]
                any_corrected = True

        if not any_corrected:
            return None, []

        corrected_query = " ".join(corrected)
        log.info("fuzzy: %r → %r", query, corrected_query)
        results = await self._search_keyword(corrected_query, category=category, limit=limit)
        if results:
            return corrected_query, results
        return None, []

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
        predicted_queries: list[str] | None = None,
        description: str | None = None,
    ) -> int:
        self._invalidate_term_dictionary()
        tags_json = json.dumps(tags) if tags else None
        await self._db.execute("DELETE FROM chunks WHERE file_path = ?", (rel_path,))
        for i, chunk in enumerate(chunks):
            # Build searchable_content: content + metadata for FTS indexing
            sc_parts = [chunk["content"]]
            if aliases:
                sc_parts.append(f"Also known as: {', '.join(aliases)}")
            if answers:
                sc_parts.append(f"Questions this document answers: {' | '.join(answers)}")
            if predicted_queries:
                sc_parts.append(f"Predicted search queries: {' | '.join(predicted_queries)}")
            if description:
                sc_parts.append(description)
            if tags:
                sc_parts.append(f"Keywords: {', '.join(tags)}")
            sc_parts.append(f"Source: {rel_path}")
            # Expand compound terms so component words are searchable
            expanded = _expand_compound_terms(chunk["content"])
            if expanded:
                sc_parts.append(f"Expanded terms: {expanded}")
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

    async def get_all_file_paths(self) -> set[str]:
        """Return all distinct file_path values from the chunks table."""
        if not await self._table_exists("chunks"):
            return set()
        rows = await self._db.execute_fetchall("SELECT DISTINCT file_path FROM chunks")
        return {r[0] for r in rows}

    async def delete_docs(self, paths: list[str]) -> int:
        """Delete chunks and links for the given file paths.

        Returns number of paths deleted.
        """
        if not paths:
            return 0
        has_links = await self._table_exists("links")
        for path in paths:
            await self._db.execute("DELETE FROM chunks WHERE file_path = ?", (path,))
            if has_links:
                await self._db.execute(
                    "DELETE FROM links WHERE source_path = ? OR target_path = ?",
                    (path, path),
                )
        await self._db.commit()
        return len(paths)

    # -- helpers -----------------------------------------------------------

    async def _table_exists(self, name: str) -> bool:
        rows = await self._db.execute_fetchall(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        )
        return len(rows) > 0
