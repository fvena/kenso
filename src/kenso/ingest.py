"""Markdown ingestion: scan, parse frontmatter, chunk by headings, load into SQLite."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "IngestResult",
    "content_hash",
    "parse_frontmatter",
    "extract_relates_to",
    "extract_title",
    "chunk_by_headings",
    "scan_files",
    "ingest_path",
]

log = logging.getLogger("kenso")

_FM_KV_RE = re.compile(r"^(\w+)\s*:\s*(.+)$", re.MULTILINE)
_H1_RE = re.compile(r"^# (.+)$", re.MULTILINE)
_H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_FENCED_CODE_RE = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)


@dataclass
class IngestResult:
    path: str
    chunks: int
    action: str  # "ingested", "unchanged", "skipped", "error"
    detail: str = ""
    title: str | None = None
    category: str | None = None


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── Frontmatter ──────────────────────────────────────────────────────


def _parse_frontmatter_simple(fm_block: str) -> dict[str, str]:
    """Fallback regex parser for simple key: value pairs."""
    meta: dict[str, str] = {}
    for match in _FM_KV_RE.finditer(fm_block):
        key, val = match.group(1).strip(), match.group(2).strip().strip("\"'")
        meta[key] = val
    return meta


def parse_frontmatter(markdown: str) -> tuple[dict, str]:
    """Parse YAML frontmatter. Uses PyYAML if available, regex fallback otherwise.

    Returns (metadata_dict, body_without_frontmatter).
    """
    if not markdown.startswith("---"):
        return {}, markdown
    end = markdown.find("\n---", 3)
    if end == -1:
        return {}, markdown

    fm_block = markdown[4:end]
    body = markdown[end + 4 :].lstrip("\n")

    try:
        import yaml

        meta = yaml.safe_load(fm_block) or {}
        if not isinstance(meta, dict):
            meta = _parse_frontmatter_simple(fm_block)
    except ImportError:
        meta = _parse_frontmatter_simple(fm_block)
    except yaml.YAMLError:
        meta = _parse_frontmatter_simple(fm_block)

    return meta, body


def extract_relates_to(markdown: str) -> list[tuple[str, str]]:
    """Extract relates_to paths and relation types from frontmatter.

    Supports three formats:

    Comma-separated (all get default 'related' type)::

        relates_to: guides/setup.md, architecture/overview.md

    YAML list of strings::

        relates_to:
          - guides/setup.md

    YAML list of dicts with typed relations::

        relates_to:
          - path: guides/setup.md
            relation: feeds_into
          - path: architecture/overview.md
            relation: implements_with

    Returns list of (path, relation_type) tuples.
    """
    if not markdown.startswith("---"):
        return []
    end = markdown.find("\n---", 3)
    if end == -1:
        return []

    # Try YAML parser first for full dict support
    fm_block = markdown[4:end]
    relates_raw = None
    try:
        import yaml
    except ImportError:
        yaml = None  # type: ignore[assignment]
    if yaml is not None:
        try:
            meta = yaml.safe_load(fm_block)
            if isinstance(meta, dict):
                relates_raw = meta.get("relates_to")
        except yaml.YAMLError:
            pass

    if relates_raw is not None:
        return _parse_relates_raw(relates_raw)

    # Fallback: regex parsing (comma-separated or simple YAML list)
    lines = fm_block.split("\n")
    paths: list[tuple[str, str]] = []
    in_list = False

    for line in lines:
        match = re.match(r"^relates_to\s*:\s*(.+)$", line)
        if match:
            val = match.group(1).strip()
            if val:
                for v in val.split(","):
                    v = v.strip().strip("\"'- ")
                    if v and "*" not in v and "?" not in v:
                        paths.append((v, "related"))
                in_list = False
                continue

        if re.match(r"^relates_to\s*:\s*$", line):
            in_list = True
            continue

        if in_list:
            item = re.match(r"^\s+-\s+(.+)$", line)
            if item:
                v = item.group(1).strip().strip("\"'")
                if v and "*" not in v and "?" not in v:
                    paths.append((v, "related"))
            elif line.strip():
                in_list = False

    return paths


def _parse_relates_raw(relates_raw) -> list[tuple[str, str]]:
    """Parse the relates_to value from YAML into (path, relation) tuples."""
    results: list[tuple[str, str]] = []

    if isinstance(relates_raw, str):
        # Comma-separated string
        for v in relates_raw.split(","):
            v = v.strip()
            if v and "*" not in v and "?" not in v:
                results.append((v, "related"))

    elif isinstance(relates_raw, list):
        for item in relates_raw:
            if isinstance(item, str):
                v = item.strip()
                if v and "*" not in v and "?" not in v:
                    results.append((v, "related"))
            elif isinstance(item, dict):
                path = str(item.get("path", "")).strip()
                relation = str(item.get("relation", "related")).strip()
                if path and "*" not in path and "?" not in path:
                    results.append((path, relation))

    return results


def extract_title(markdown: str) -> str | None:
    hit = _H1_RE.search(markdown)
    return hit.group(1).strip() if hit else None


# ── Protected ranges (code blocks, tables) ───────────────────────────


def _find_protected_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []

    # Fenced code blocks
    in_fence = False
    fence_start = 0
    fence_marker = ""
    for match in _FENCED_CODE_RE.finditer(text):
        marker = match.group(1)
        if not in_fence:
            in_fence = True
            fence_start = match.start()
            fence_marker = marker[0]
        elif marker[0] == fence_marker:
            ranges.append((fence_start, match.end()))
            in_fence = False
    if in_fence:
        ranges.append((fence_start, len(text)))

    # Tables
    lines = text.split("\n")
    pos = 0
    table_start = -1
    for line in lines:
        stripped = line.strip()
        is_table = stripped.startswith("|") and stripped.endswith("|")
        if is_table and table_start == -1:
            table_start = pos
        elif not is_table and table_start != -1:
            ranges.append((table_start, pos))
            table_start = -1
        pos += len(line) + 1
    if table_start != -1:
        ranges.append((table_start, len(text)))

    return sorted(ranges)


def _is_in_protected(pos: int, ranges: list[tuple[int, int]]) -> bool:
    for start, end in ranges:
        if start <= pos < end:
            return True
        if start > pos:
            break
    return False


# ── Paragraph splitting ──────────────────────────────────────────────


def _split_paragraphs_safe(text: str, max_size: int) -> list[str]:
    """Split at paragraph boundaries, never inside code blocks or tables."""
    if len(text) <= max_size:
        return [text]

    protected = _find_protected_ranges(text)

    split_points: list[int] = []
    idx = 0
    while True:
        idx = text.find("\n\n", idx)
        if idx == -1:
            break
        if not _is_in_protected(idx, protected):
            split_points.append(idx)
        idx += 2

    if not split_points:
        return [text]

    boundaries = [0] + [sp + 2 for sp in split_points] + [len(text)]
    segments = [text[boundaries[i] : boundaries[i + 1]] for i in range(len(boundaries) - 1)]

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for seg in segments:
        seg_len = len(seg)
        if current_parts and current_len + seg_len > max_size:
            chunk_text = "".join(current_parts).strip()
            if chunk_text:
                chunks.append(chunk_text)
            current_parts = [seg]
            current_len = seg_len
        else:
            current_parts.append(seg)
            current_len += seg_len

    if current_parts:
        chunk_text = "".join(current_parts).strip()
        if chunk_text:
            chunks.append(chunk_text)

    return chunks if chunks else [text]


# ── Heading-based chunking ───────────────────────────────────────────


def _split_section_by_subheadings(
    content: str,
    doc_title: str,
    parent_title: str,
    level: int,
    max_size: int,
) -> list[dict]:
    """Split an oversized section by sub-headings (H3 inside H2, etc.)."""
    sub_re = re.compile(rf"^{'#' * (level + 1)} (.+)$", re.MULTILINE)
    matches = list(sub_re.finditer(content))

    full_parent = f"{doc_title} > {parent_title}"

    if not matches:
        parts = _split_paragraphs_safe(content, max_size)
        if len(parts) == 1:
            return [
                {"title": full_parent, "content": content.strip(), "section_path": full_parent}
            ]
        return [
            {
                "title": full_parent if i == 0 else f"{full_parent} (cont.)",
                "content": p,
                "section_path": full_parent,
            }
            for i, p in enumerate(parts)
            if p.strip()
        ]

    chunks = []
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section = content[start:end].strip()

        if len(section) < 20:
            continue

        full_title = f"{doc_title} > {title}"

        if len(section) > max_size and level + 1 < 4:
            chunks.extend(
                _split_section_by_subheadings(section, doc_title, title, level + 1, max_size)
            )
        elif len(section) > max_size:
            parts = _split_paragraphs_safe(section, max_size)
            for j, p in enumerate(parts):
                if not p.strip():
                    continue
                chunks.append(
                    {
                        "title": full_title if j == 0 else f"{full_title} (cont.)",
                        "content": p,
                        "section_path": full_title,
                    }
                )
        else:
            chunks.append({"title": full_title, "content": section, "section_path": full_title})

    return chunks


def _apply_overlap(chunks: list[dict], overlap: int) -> list[dict]:
    """Prepend last N chars of the previous chunk (on word boundary) to each chunk.

    Skips the first chunk and any preamble chunk (title ending with "— Overview").
    """
    if overlap <= 0 or len(chunks) < 2:
        return chunks

    for i in range(1, len(chunks)):
        # Don't apply overlap to preamble chunks
        if chunks[i]["title"].endswith("— Overview"):
            continue
        prev_content = chunks[i - 1]["content"]
        if len(prev_content) <= overlap:
            tail = prev_content
        else:
            # Cut at word boundary
            tail = prev_content[-overlap:]
            space_idx = tail.find(" ")
            if space_idx != -1:
                tail = tail[space_idx + 1 :]
        if tail.strip():
            chunks[i]["content"] = tail.rstrip() + "\n\n" + chunks[i]["content"]

    return chunks


def chunk_by_headings(
    markdown: str, file_path: str, max_chunk_size: int = 4000, chunk_overlap: int = 0
) -> list[dict]:
    """Split markdown into chunks by H2 headings.

    Strategy:
    1. Split at H2 boundaries (primary)
    2. Oversized H2 sections split at H3, then H4
    3. Still too large: split at paragraph boundaries
    4. Never splits inside fenced code blocks or tables
    """
    matches = list(_H2_RE.finditer(markdown))
    doc_title = extract_title(markdown) or Path(file_path).stem

    if not matches:
        stripped = markdown.strip()
        if len(stripped) <= max_chunk_size:
            return [{"title": doc_title, "content": stripped, "section_path": doc_title}]
        parts = _split_paragraphs_safe(stripped, max_chunk_size)
        return [
            {
                "title": doc_title if i == 0 else f"{doc_title} (cont.)",
                "content": p,
                "section_path": doc_title,
            }
            for i, p in enumerate(parts)
            if p.strip()
        ] or [{"title": doc_title, "content": stripped, "section_path": doc_title}]

    chunks = []

    # Capture content before first H2 as preamble
    preamble = markdown[: matches[0].start()].strip()
    preamble = _H1_RE.sub("", preamble).strip()  # Remove H1 (already in doc_title)
    merge_preamble = ""
    if len(preamble) >= 50:
        chunks.append(
            {
                "title": f"{doc_title} — Overview",
                "content": preamble,
                "section_path": doc_title,
            }
        )
    elif preamble:
        # Short preamble: merge into first section chunk
        merge_preamble = preamble

    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        content = markdown[start:end].strip()

        if len(content) < 20:
            continue

        # Fix 2.4: Use full section_path as chunk title for FTS5 weight
        full_title = f"{doc_title} > {title}"

        if len(content) > max_chunk_size:
            chunks.extend(
                _split_section_by_subheadings(content, doc_title, title, 2, max_chunk_size)
            )
        else:
            chunks.append(
                {
                    "title": full_title,
                    "content": content,
                    "section_path": f"{doc_title} > {title}",
                }
            )

    # Merge short preamble into first section chunk
    if merge_preamble and chunks:
        # Find first non-overview chunk (or first chunk if no overview)
        target = 0
        for idx, c in enumerate(chunks):
            if not c["title"].endswith("— Overview"):
                target = idx
                break
        chunks[target]["content"] = merge_preamble + "\n\n" + chunks[target]["content"]

    result = chunks or [
        {"title": doc_title, "content": markdown.strip(), "section_path": doc_title}
    ]
    if chunk_overlap > 0:
        result = _apply_overlap(result, chunk_overlap)
    return result


# ── File scanning ────────────────────────────────────────────────────


def _load_kensoignore(root: Path) -> list[str] | None:
    """Load .kensoignore patterns from the root directory.

    Returns parsed pattern lines, or None if no .kensoignore file exists.
    """
    ignore_path = root / ".kensoignore"
    if not ignore_path.is_file():
        return None
    try:
        text = ignore_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.warning("Could not read .kensoignore: %s", e)
        return None
    patterns: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns if patterns else None


def _match_kensoignore(rel_path: str, patterns: list[str]) -> bool:
    """Check if a relative path matches any .kensoignore pattern.

    Supports:
    - Negation with ! prefix (un-ignores a file)
    - Trailing / for directory-only matching
    - Glob patterns via pathlib.PurePath.match()
    """
    from pathlib import PurePosixPath

    path = PurePosixPath(rel_path)
    ignored = False
    for pattern in patterns:
        negate = False
        p = pattern
        if p.startswith("!"):
            negate = True
            p = p[1:]

        dir_only = p.endswith("/")
        if dir_only:
            p = p.rstrip("/")
            # For directory-only patterns, check if any parent matches
            matched = any(PurePosixPath(part).match(p) for part in path.parents)
            if not matched:
                # Also check if the pattern matches a path component prefix
                matched = any(p in str(parent) for parent in path.parents)
        else:
            matched = path.match(p)

        if matched:
            ignored = not negate

    return ignored


def scan_files(root: Path) -> list[Path]:
    """Recursively find all .md files under root, sorted.

    If a .kensoignore file exists in root, filters out matching paths.
    """
    if root.is_file() and root.suffix.lower() == ".md":
        return [root]

    files = sorted(root.rglob("*.md"))

    patterns = _load_kensoignore(root)
    if patterns is None:
        return files

    filtered: list[Path] = []
    for f in files:
        rel = str(f.relative_to(root))
        if not _match_kensoignore(rel, patterns):
            filtered.append(f)

    return filtered


# ── Ingestion pipeline ───────────────────────────────────────────────


async def ingest_path(
    config,
    root: str,
) -> list[IngestResult]:
    """Scan a path for markdown files and load them into the database."""
    root_path = Path(root).resolve()
    if not root_path.exists():
        return [IngestResult(path=root, chunks=0, action="error", detail="Path does not exist")]

    files = scan_files(root_path)
    if not files:
        return [IngestResult(path=root, chunks=0, action="skipped", detail="No .md files found")]

    base = root_path.parent if root_path.is_file() else root_path
    results: list[IngestResult] = []

    from kenso.backend import Backend

    backend = Backend(config)
    await backend.startup()

    try:
        table_exists = await backend.has_column("chunks", "file_path")
        if not table_exists:
            await backend.init_schema()

        has_hash = await backend.has_column("chunks", "content_hash")
        total_files = len(files)

        for idx, f in enumerate(files, 1):
            rel = str(f.relative_to(base))
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                if len(text.strip()) < 50:
                    results.append(
                        IngestResult(path=rel, chunks=0, action="skipped", detail="<50 chars")
                    )
                    continue
                digest = content_hash(text)
            except OSError as e:
                results.append(IngestResult(path=rel, chunks=0, action="error", detail=str(e)))
                continue

            frontmatter, body = parse_frontmatter(text)

            # Skip unchanged files
            if has_hash:
                existing = await backend.get_content_hash(rel)
                if existing == digest:
                    doc_chunks = await backend.get_doc(rel)
                    results.append(
                        IngestResult(path=rel, chunks=len(doc_chunks), action="unchanged")
                    )
                    continue

            title = extract_title(body) or frontmatter.get("title") or f.stem
            category = frontmatter.get("category") or (
                f.parent.name if f.parent != base else "general"
            )
            audience = frontmatter.get("audience", "all")

            # Handle tags as YAML list or comma-separated string
            raw_tags = frontmatter.get("tags", "")
            if isinstance(raw_tags, list):
                tags = [str(t).strip() for t in raw_tags if str(t).strip()]
            elif isinstance(raw_tags, str) and raw_tags:
                tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
            else:
                tags = None

            chunks = chunk_by_headings(
                body, rel, max_chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap
            )

            # Extract frontmatter metadata for searchable_content
            raw_aliases = frontmatter.get("aliases")
            aliases = [str(a) for a in raw_aliases] if isinstance(raw_aliases, list) else None
            raw_answers = frontmatter.get("answers")
            answers = [str(a) for a in raw_answers] if isinstance(raw_answers, list) else None
            raw_pq = frontmatter.get("predicted_queries")
            predicted_queries = [str(q) for q in raw_pq] if isinstance(raw_pq, list) else None
            fm_description = frontmatter.get("description")
            fm_description = (
                fm_description.strip()
                if isinstance(fm_description, str) and fm_description.strip()
                else None
            )

            count = await backend.ingest_file(
                rel,
                chunks,
                title=title,
                category=category,
                audience=audience,
                tags=tags,
                content_hash=digest,
                aliases=aliases,
                answers=answers,
                predicted_queries=predicted_queries,
                description=fm_description,
            )

            link_targets = extract_relates_to(text)
            if link_targets:
                try:
                    await backend.insert_typed_links(rel, link_targets)
                except (OSError, Exception) as exc:
                    log.warning("insert_links failed for %s: %s", rel, exc)

            results.append(
                IngestResult(
                    path=rel, chunks=count, action="ingested", title=title, category=category
                )
            )
            log.info("[%d/%d] ingested: %s (%d chunks)", idx, total_files, rel, count)

        # Clean up stale documents (files removed from disk).
        # Only clean when ingesting a directory (not a single file).
        # Scope to paths whose parent directory matches a live path's parent,
        # so ingesting a subdirectory doesn't delete entries from siblings.
        if root_path.is_dir():
            live_paths = {str(f.relative_to(base)) for f in files}
            db_paths = await backend.get_all_file_paths()

            # Compute directory prefixes covered by our scan
            live_dirs: set[str] = set()
            for p in live_paths:
                live_dirs.add(p.rsplit("/", 1)[0] if "/" in p else "")

            stale = []
            for db_path in sorted(db_paths - live_paths):
                db_dir = db_path.rsplit("/", 1)[0] if "/" in db_path else ""
                if db_dir in live_dirs:
                    stale.append(db_path)

            if stale:
                await backend.delete_docs(stale)
                for sp in stale:
                    results.append(IngestResult(path=sp, chunks=0, action="removed"))
                    log.info("removed stale: %s", sp)

    finally:
        await backend.shutdown()

    return results
