# Kenso Search Quality Audit

Complete inventory of every factor that influences whether the right document appears in search results, and how high it ranks.

## Part 1: Factor Inventory

### A. File Discovery and Filtering

#### A1. File extension filter — only `.md` files

- **Where:** `ingest.py:scan_files()` line 445
- **Who controls:** Hardcoded
- **Good:** All markdown docs are found
- **Bad/absent:** Non-`.md` files (`.mdx`, `.txt`, `.rst`) are silently excluded — no warning
- **Exact values:** `*.md` glob via `rglob("*.md")`

#### A2. Minimum content threshold — 50 characters

- **Where:** `ingest.py:ingest_path()` line 484
- **Who controls:** Hardcoded
- **Good:** Tiny stub files are skipped, reducing noise
- **Bad/absent:** Files with <50 chars (after stripping) get `action="skipped"`. Short but valid docs (e.g., a redirect or glossary entry) are lost
- **Exact values:** `len(text.strip()) < 50` -> skip

#### A3. Recursive scan — `rglob`

- **Where:** `ingest.py:scan_files()` line 445
- **Who controls:** Nobody (Python's `rglob`)
- **Good:** Finds all nested `.md` files
- **Bad/absent:** `rglob("*.md")` does NOT follow symlinks by default in Python <3.13. Hidden directories (`.hidden/`) ARE traversed — no dotfile filter exists. No `.kensoignore` or exclusion mechanism
- **Exact values:** No depth limit, no exclusion patterns

#### A4. Single file ingestion

- **Where:** `ingest.py:scan_files()` lines 443-444
- **Who controls:** User (CLI argument)
- **Good:** A single `.md` file path works directly
- **Bad/absent:** If a non-`.md` file is passed, returns empty list -> `"No .md files found"`

#### A5. Content hash — skip unchanged files

- **Where:** `ingest.py:ingest_path()` lines 495-499, `content_hash()` line 39
- **Who controls:** Automatic
- **Good:** Unchanged files skip re-indexing -> faster incremental ingests
- **Bad/absent:** Hash is SHA-256 of entire raw file content (including frontmatter). Any whitespace or metadata change triggers full re-index. Hash is truncated to first 16 hex chars
- **Exact values:** `hashlib.sha256(text.encode()).hexdigest()[:16]`

### B. Parsing

#### B1. Frontmatter detection — `---` delimiters

- **Where:** `ingest.py:parse_frontmatter()` lines 59-61
- **Who controls:** Author
- **Good:** Standard YAML frontmatter is parsed
- **Bad/absent:** Must start at exact position 0 (`markdown.startswith("---")`). A single leading newline or BOM breaks detection -> returns empty `{}` and the full text as body. Closing delimiter found via `markdown.find("\n---", 3)` — requires newline before `---`
- **Exact values:** Opening: bytes 0-2 must be `---`. Closing: first `\n---` after position 3

#### B2. Frontmatter parser — YAML with regex fallback

- **Where:** `ingest.py:parse_frontmatter()` lines 68-76
- **Who controls:** System dependency
- **Good:** With PyYAML installed, full YAML (lists, nested dicts) works
- **Bad/absent:** Without PyYAML, falls back to regex `^(\w+)\s*:\s*(.+)$` — only flat key-value pairs, no lists, no multi-line values. YAML parse errors also fall back to regex. Regex strips surrounding `"'` quotes from values
- **Exact values:** Regex: `r"^(\w+)\s*:\s*(.+)$"` with `re.MULTILINE`

#### B3. Title resolution priority

- **Where:** `ingest.py:ingest_path()` line 502
- **Who controls:** Author
- **Good:** H1 in body takes priority, giving authors control via content
- **Bad/absent:** Priority is: `extract_title(body)` -> `frontmatter.get("title")` -> `f.stem`. Note: `extract_title` searches the BODY (frontmatter already stripped), finding first `# heading`. If no H1 and no frontmatter title, filename stem is used (e.g., `my-guide` not `my-guide.md`)
- **Exact values:** Order: H1 in body > `title` frontmatter key > filename stem

#### B4. Category resolution

- **Where:** `ingest.py:ingest_path()` line 503
- **Who controls:** Author (frontmatter) or directory structure
- **Good:** Explicit category in frontmatter overrides directory
- **Bad/absent:** Fallback: `f.parent.name` if file is in a subdirectory, `"general"` if file is at the root. Category is set per-file, applied to ALL chunks of that file. No validation or normalization (case-sensitive)
- **Exact values:** `frontmatter.get("category")` -> `f.parent.name` (if parent != base) -> `"general"`

#### B5. Audience field

- **Where:** `ingest.py:ingest_path()` line 504
- **Who controls:** Author (frontmatter)
- **Good:** Stored in DB per chunk
- **Bad/absent:** Default `"all"`. Never used in search filtering or ranking — purely metadata. Not indexed in FTS5
- **Exact values:** Default: `"all"`

#### B6. Tags parsing

- **Where:** `ingest.py:ingest_path()` lines 507-513
- **Who controls:** Author (frontmatter)
- **Good:** Supports both YAML list `[tag1, tag2]` and comma-separated string `"tag1, tag2"`
- **Bad/absent:** If not a list or non-empty string, tags become `None`. Tags are stored as JSON in the `tags` column AND injected into `searchable_content` as `"Keywords: tag1, tag2"`. Tags column is FTS5-indexed with weight 7.0
- **Exact values:** JSON serialized for DB storage, comma-joined for searchable_content

#### B7. Aliases extraction

- **Where:** `ingest.py:ingest_path()` lines 518-519
- **Who controls:** Author (frontmatter)
- **Good:** Alternative names are injected into `searchable_content`
- **Bad/absent:** Must be a YAML list. If not a list type, aliases are `None` and silently ignored. Injected as `"Also known as: alias1, alias2"` — this exact phrasing is indexed
- **Exact values:** Format: `"Also known as: {', '.join(aliases)}"`

#### B8. Answers extraction

- **Where:** `ingest.py:ingest_path()` lines 520-521
- **Who controls:** Author (frontmatter)
- **Good:** Question phrases are injected into `searchable_content`, improving recall for question-style queries
- **Bad/absent:** Must be a YAML list. Injected as `"Questions this document answers: q1 | q2"`
- **Exact values:** Format: `"Questions this document answers: {' | '.join(answers)}"`

#### B9. Description extraction

- **Where:** `ingest.py:ingest_path()` lines 522-523
- **Who controls:** Author (frontmatter)
- **Good:** Summary text is appended to `searchable_content`
- **Bad/absent:** Must be a non-empty string after stripping. Appended as plain text (no label prefix, unlike aliases/answers/tags)
- **Exact values:** Appended directly, no formatting wrapper

#### B10. `relates_to` link extraction

- **Where:** `ingest.py:extract_relates_to()` lines 81-159, `_parse_relates_raw()` lines 162-185
- **Who controls:** Author (frontmatter)
- **Good:** Three formats supported: comma-separated string, YAML list of strings, YAML list of dicts with `path`/`relation` keys
- **Bad/absent:** Glob patterns (`*`, `?`) in paths are silently filtered out (lines 141, 154, 170, 177, 183). Default relation type is `"related"`. Links are unidirectional in storage (source->target) but queried bidirectionally
- **Exact values:** Default relation: `"related"`. Paths with `*` or `?` excluded

### C. Chunking

#### C1. Primary split — H2 headings

- **Where:** `ingest.py:chunk_by_headings()` lines 383, 409-429
- **Who controls:** Author (document structure)
- **Good:** Each H2 section becomes a separate chunk, enabling section-level search precision
- **Bad/absent:** Documents without H2 headings become a single chunk (or paragraph-split if oversized). The H2 regex is `^## (.+)$` with `re.MULTILINE` — requires exactly `## ` prefix at line start
- **Exact values:** Regex: `r"^## (.+)$"`

#### C2. Preamble / Overview chunk

- **Where:** `ingest.py:chunk_by_headings()` lines 400-407
- **Who controls:** Author (content before first H2)
- **Good:** Intro content is preserved as a separate searchable chunk titled `"{doc_title} — Overview"`
- **Bad/absent:** Only created if preamble >= 50 characters after stripping H1. Below 50 chars, preamble content is LOST (not merged into first section chunk)
- **Exact values:** Minimum: 50 characters. Title suffix: `" — Overview"`

#### C3. Minimum section size

- **Where:** `ingest.py:chunk_by_headings()` line 415, `_split_section_by_subheadings()` line 323
- **Who controls:** Hardcoded
- **Good:** Tiny sections (just a heading) are filtered out
- **Bad/absent:** Sections with content < 20 characters are silently dropped via `if len(content) < 20: continue`
- **Exact values:** `< 20` characters -> skipped

#### C4. Maximum chunk size

- **Where:** `config.py` line 49, `ingest.py:chunk_by_headings()` line 374
- **Who controls:** Admin (`KENSO_CHUNK_SIZE` env var)
- **Good:** Oversized sections trigger sub-splitting
- **Bad/absent:** Default 4000 chars. If a section exceeds this, it's split by H3 -> H4 -> paragraph boundaries. No minimum chunk size enforced after splitting (except the 20-char filter)
- **Exact values:** Default: `4000` chars. Env var: `KENSO_CHUNK_SIZE`

#### C5. Sub-heading split cascade — H3, H4

- **Where:** `ingest.py:_split_section_by_subheadings()` lines 296-344
- **Who controls:** Author (heading structure) + hardcoded depth limit
- **Good:** Progressively finer splitting preserves section boundaries
- **Bad/absent:** Splits H2->H3->H4 (levels 2, 3, up to `level + 1 < 4` i.e., stops at H4). H5+ headings are never used as split points. If still oversized after H4, falls to paragraph splitting
- **Exact values:** Max heading depth: H4 (level 4). Condition: `level + 1 < 4`

#### C6. Paragraph-safe splitting

- **Where:** `ingest.py:_split_paragraphs_safe()` lines 246-290
- **Who controls:** Hardcoded
- **Good:** Splits at `\n\n` boundaries, respecting code blocks and tables
- **Bad/absent:** If no `\n\n` found (or all are inside protected ranges), returns the entire text as one chunk regardless of size — no hard split
- **Exact values:** Split point: `\n\n` (double newline)

#### C7. Protected ranges — code blocks

- **Where:** `ingest.py:_find_protected_ranges()` lines 199-213
- **Who controls:** Author (code fences)
- **Good:** Fenced code blocks (`` ``` `` or `~~~`) are never split mid-block
- **Bad/absent:** Matching requires 3+ backticks or tildes at line start. Opening and closing fence must use the same character. Unclosed fence extends protection to end of document. Indented code blocks (4 spaces) are NOT protected
- **Exact values:** Regex: `` r"^(`{3,}|~{3,})" ``

#### C8. Protected ranges — tables

- **Where:** `ingest.py:_find_protected_ranges()` lines 216-229
- **Who controls:** Author (table formatting)
- **Good:** Consecutive lines starting and ending with `|` are protected from splitting
- **Bad/absent:** Detection: `stripped.startswith("|") and stripped.endswith("|")`. Tables not using `|` borders aren't protected. A line break in a table ends the protection
- **Exact values:** Must start AND end with `|` after stripping

#### C9. Chunk overlap

- **Where:** `ingest.py:_apply_overlap()` lines 347-371, `config.py` line 50
- **Who controls:** Admin (`KENSO_CHUNK_OVERLAP` env var)
- **Good:** Overlapping content provides context continuity between chunks
- **Bad/absent:** Default is `0` (no overlap). When enabled, last N characters of previous chunk (cut at word boundary) are prepended to current chunk. Skips overview chunks (title ending with `"— Overview"`). Applied after all chunking is done
- **Exact values:** Default: `0`. Env var: `KENSO_CHUNK_OVERLAP`. Word boundary: first space in tail substring

#### C10. Section path construction

- **Where:** `ingest.py:chunk_by_headings()` lines 419, 428; `_split_section_by_subheadings()` lines 303, 309, 326
- **Who controls:** Author (heading text)
- **Good:** Hierarchical path like `"Doc Title > Section"` is stored in FTS5 with weight 8.0
- **Bad/absent:** Overview chunks get `section_path = doc_title` (no `>` separator). Sub-split chunks get `"{doc_title} > {sub_title}"` — note: intermediate heading levels are collapsed (H2->H4 skips H3 in the path). Continuation chunks (`(cont.)`) share the parent's section_path
- **Exact values:** Separator: `" > "`. Weight in FTS5: 8.0

#### C11. Chunk title construction

- **Where:** `ingest.py:chunk_by_headings()` line 419; `_split_section_by_subheadings()` lines 308, 311, 326, 337
- **Who controls:** Author (heading text)
- **Good:** Title is `"{doc_title} > {section_title}"`, indexed in FTS5 at highest weight (10.0)
- **Bad/absent:** For documents without H2, title is just `doc_title`. Continuation chunks get `"{title} (cont.)"`. Overview chunks get `"{doc_title} — Overview"`. These titles are the PRIMARY ranking signal due to 10x weight
- **Exact values:** Weight in FTS5: 10.0

### D. Index Construction

#### D1. FTS5 table schema

- **Where:** `schema.py` lines 33-42
- **Who controls:** Hardcoded
- **Good:** Five columns with differentiated weights enable field-specific ranking
- **Bad/absent:** Content table is `chunks`, FTS5 is `chunks_fts` with `content='chunks', content_rowid='id'`
- **Exact values:**
  - `title` — weight 10.0
  - `section_path` — weight 8.0
  - `tags` — weight 7.0
  - `category` — weight 5.0
  - `searchable_content` — weight 1.0

#### D2. FTS5 tokenizer

- **Where:** `schema.py` line 41
- **Who controls:** Hardcoded
- **Good:** Porter stemmer + unicode61 handles inflections and diacritics
- **Bad/absent:** Tokenizer string: `'porter unicode61 remove_diacritics 2'`. `remove_diacritics 2` means diacritics are removed from Latin characters only (not all Unicode). Porter stemmer handles English only. No CJK tokenizer
- **Exact values:** `tokenize='porter unicode61 remove_diacritics 2'`

#### D3. Searchable content formula

- **Where:** `backend.py:ingest_file()` lines 503-514
- **Who controls:** Author (content + frontmatter)
- **Good:** Aggregates content plus metadata into one searchable field
- **Bad/absent:** Parts joined by `"\n\n"`. Always includes `"Source: {rel_path}"` at the end. Order: content -> aliases -> answers -> description -> tags -> source path
- **Exact values:**
  1. `chunk["content"]`
  2. `"Also known as: {', '.join(aliases)}"` (if aliases)
  3. `"Questions this document answers: {' | '.join(answers)}"` (if answers)
  4. `description` (if present, raw text)
  5. `"Keywords: {', '.join(tags)}"` (if tags)
  6. `"Source: {rel_path}"` (always)

#### D4. FTS5 sync triggers

- **Where:** `schema.py` lines 44-60
- **Who controls:** Hardcoded
- **Good:** INSERT, DELETE, UPDATE on `chunks` automatically update `chunks_fts`
- **Bad/absent:** Triggers use `COALESCE(col, '')` for nullable columns — null values become empty strings in FTS. The searchable_content fallback is `COALESCE(new.searchable_content, new.content)` — if searchable_content is null, raw content is indexed instead
- **Exact values:** Three triggers: `chunks_ai` (after insert), `chunks_ad` (after delete), `chunks_au` (after update)

#### D5. Compound term expansion — camelCase/snake_case

- **Where:** `backend.py:_expand_compound_word()` lines 22-39
- **Who controls:** Hardcoded
- **Good:** `orderMatchingEngine` -> `["orderMatchingEngine", "order", "matching", "engine"]`; `order_matching` -> `["order_matching", "order", "matching"]`
- **Bad/absent:** Only applies to query terms, NOT to indexed content. Splitting regex for camelCase: `r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])'`. Hyphenated terms (`foo-bar`) and dotted terms (`foo.bar`) are NOT expanded — only `_` and camelCase boundaries
- **Exact values:** camelCase regex: `_CAMEL_SPLIT`. snake_case: split on `"_"`

#### D6. File re-indexing on change

- **Where:** `backend.py:ingest_file()` line 501
- **Who controls:** Automatic
- **Good:** Old chunks for a file are fully deleted before re-inserting
- **Bad/absent:** `DELETE FROM chunks WHERE file_path = ?` — deletes ALL chunks for that file, then re-inserts. No partial update. Links are also fully replaced (`DELETE FROM links WHERE source_path = ?`)

### E. Query Processing

#### E1. Query sanitization

- **Where:** `backend.py:_to_fts5_queries()` lines 42-78
- **Who controls:** Hardcoded
- **Good:** FTS5 special characters are stripped: `" * ( ) - + ^ :`
- **Bad/absent:** Each word is wrapped in double quotes after cleaning (`f'"{cleaned}"'`). This makes each term a literal phrase match, disabling FTS5 prefix matching (except for the explicit prefix fallback)
- **Exact values:** Regex: `r'["\*\(\)\-\+\^:]'`

#### E2. Search cascade — multi-stage FTS5 queries

- **Where:** `backend.py:_to_fts5_queries()` lines 72-78, `_search_keyword()` lines 252-267
- **Who controls:** Hardcoded
- **Good:** Progressive broadening: strict -> proximity -> broad
- **Bad/absent:** Cascade stages for multi-word queries:
  1. **AND** — all terms must appear: `"term1" AND "term2" AND ...`
  2. **NEAR** — terms within 10 tokens (only if 2-4 terms): `NEAR("term1" "term2", 10)`
  3. **OR** — any term: `"term1" OR "term2" OR ...`

  Cascade stops when `len(results) >= min_results`. If no stage meets threshold, last stage's results are returned (even if empty)
- **Exact values:** NEAR distance: `10` tokens. NEAR only for 2-4 safe terms. Min results to stop cascade: `min(3, limit)`

#### E3. Single-word prefix fallback

- **Where:** `backend.py:_to_fts5_queries()` lines 64-70
- **Who controls:** Hardcoded
- **Good:** Single-term queries get a prefix variant: `"term"*` as a second cascade stage
- **Bad/absent:** Only applied when: single word, no spaces in original text, cleaned word >= 3 characters. Cascade: exact `"term"` -> prefix `"term"*`
- **Exact values:** Minimum length for prefix: 3 characters

#### E4. Category filtering

- **Where:** `backend.py:search()` lines 134-136, `_execute_fts()` lines 287-289
- **Who controls:** User (query parameter)
- **Good:** Exact-match category filter via SQL `WHERE`
- **Bad/absent:** `"all"`, `""`, `"none"`, `"*"` are all treated as "no filter" (case-insensitive). Category comparison in SQL is case-sensitive. Filter is applied at the SQL level, not post-query
- **Exact values:** No-filter values: `("all", "", "none", "*")`

#### E5. Fetch limit for candidates

- **Where:** `backend.py:search()` line 139
- **Who controls:** Hardcoded multiplier, admin controls base limit
- **Good:** Fetches 3x the requested limit for dedup/rerank headroom
- **Bad/absent:** `fetch_limit = limit * 3`. If the user requests 5, 15 candidates are fetched. This is the pool available for deduplication and reranking
- **Exact values:** Multiplier: `3x`

#### E6. Search limit capping

- **Where:** `server.py:search_docs()` line 109, `config.py` line 51
- **Who controls:** Admin (`KENSO_SEARCH_LIMIT_MAX` env var)
- **Good:** Prevents excessive result sets
- **Bad/absent:** `limit = max(1, min(cfg.search_limit_max, limit))`. Default max: 20. Minimum: 1
- **Exact values:** Default max: `20`. Env var: `KENSO_SEARCH_LIMIT_MAX`

### F. Scoring and Ranking

#### F1. BM25 scoring with custom column weights

- **Where:** `backend.py:_execute_fts()` line 279
- **Who controls:** Hardcoded
- **Good:** Weighted BM25 across 5 columns provides field-aware ranking
- **Bad/absent:** `bm25(chunks_fts, 10.0, 8.0, 7.0, 5.0, 1.0)`. BM25 internal parameters (k1, b) are SQLite defaults (not customized). Score is negated (`-float(r[4])`) because SQLite's bm25() returns negative values (lower = better)
- **Exact values:** Weights: title=10.0, section_path=8.0, tags=7.0, category=5.0, searchable_content=1.0. BM25 k1/b: SQLite defaults (k1=1.2, b=0.75)

#### F2. Deduplication — best chunk per document

- **Where:** `backend.py:_deduplicate()` lines 164-173
- **Who controls:** Hardcoded
- **Good:** Prevents the same document from dominating results
- **Bad/absent:** Keeps only the highest-scoring chunk per `file_path`. All other chunks from that document are discarded. Results re-sorted by score after dedup
- **Exact values:** Keep: 1 chunk per file_path (highest score)

#### F3. Relation density reranking

- **Where:** `backend.py:_rerank_with_relations()` lines 175-206
- **Who controls:** Hardcoded (boost parameter)
- **Good:** Documents with more intra-result-set links get boosted — promotes topic clusters
- **Bad/absent:** Formula: `score *= (1 + 0.15 * connections)` where `connections` = number of links (both as source and target) to other documents in the current result set. Boost default: `0.15` (15% per connection). Both directions count (source->target and target->source). Skipped if links table doesn't exist or <2 results
- **Exact values:** Boost per connection: `0.15` (15%). Formula: `score * (1 + 0.15 * N)`

#### F4. Score ordering

- **Where:** `backend.py:_execute_fts()` line 291
- **Who controls:** Hardcoded
- **Good:** SQL `ORDER BY score ASC` (BM25 returns negative, lower=better) combined with negation at line 301 produces correct descending order
- **Bad/absent:** After dedup and reranking, results are re-sorted by score descending

### G. Fallbacks

#### G1. File path LIKE search

- **Where:** `backend.py:search()` lines 142-144, `_search_file_path()` lines 307-327
- **Who controls:** Hardcoded trigger condition
- **Good:** When FTS5 returns nothing and query contains `/` or `.`, falls back to file path substring matching
- **Bad/absent:** Uses SQL `LIKE %query%` — case-sensitive by default in SQLite. All matching results get a fixed score of `0.5`. No highlight. Results ordered by `file_path, chunk_index`. No dedup is applied before this fallback, but dedup runs after it
- **Exact values:** Trigger: `not results and ("/" in query or "." in query)`. Fixed score: `0.5`

### H. Tokenization Deep Dive

#### H1. Porter stemmer coverage

- **Where:** `schema.py` line 41
- **Who controls:** Hardcoded (SQLite built-in)
- **Good:** Handles English inflections: run/running/runs, configure/configuration/configured, search/searching/searches
- **Bad/absent:** English-only. Does NOT handle: irregular verbs perfectly, non-English languages, abbreviations, acronyms. Stemming applies to both indexed content and queries (both pass through the same tokenizer)
- **Exact values:** Algorithm: Porter stemmer (SQLite's built-in implementation)

#### H2. Unicode61 tokenizer

- **Where:** `schema.py` line 41
- **Who controls:** Hardcoded
- **Good:** Unicode-aware tokenization, treats non-ASCII letters as word characters
- **Bad/absent:** `remove_diacritics 2` removes diacritics from Latin script only. Token boundaries at whitespace and punctuation. Hyphenated words are split into separate tokens by the tokenizer. Dots, underscores in content are token separators
- **Exact values:** `unicode61 remove_diacritics 2`

#### H3. Compound term expansion (query-side only)

- **Where:** `backend.py:_expand_compound_word()` lines 22-39
- **Who controls:** Hardcoded
- **Good:** camelCase and snake_case in queries are expanded
- **Bad/absent:** NOT applied to indexed content. If content contains `orderMatchingEngine`, the unicode61 tokenizer will tokenize it as a single token `ordermatchingengine` (lowercased). The query expansion adds component words `order`, `matching`, `engine` which won't match the single token. However, the original compound `ordermatchingengine` is also included, so exact matches work. Content-side compound words only match if the components happen to appear separately elsewhere in the content
- **Exact values:** Expansion on underscore (`_`) and camelCase boundaries only

### I. Graph and Relations

#### I1. Links table schema

- **Where:** `schema.py` lines 62-72
- **Who controls:** Hardcoded
- **Good:** `(source_path, target_path, relation_type)` with UNIQUE constraint
- **Bad/absent:** Unidirectional storage: only the declaring document creates links. No automatic reverse link. Relation type defaults to `"related"`. Indexed on both `source_path` and `target_path`
- **Exact values:** Default relation_type: `"related"`. Unique on `(source_path, target_path, relation_type)`

#### I2. Bidirectional query traversal

- **Where:** `backend.py:get_related()` lines 360-367
- **Who controls:** Hardcoded
- **Good:** Queries both `source_path = ?` and `target_path = ?`, making links effectively bidirectional for reads
- **Bad/absent:** Direction is reported (`"outgoing"` vs `"incoming"`). Self-references are skipped. Cycle prevention via `traversed` set
- **Exact values:** Traversal max depth: capped at 3 (`max(1, min(depth, 3))` in server.py line 250)

#### I3. Relation density calculation for reranking

- **Where:** `backend.py:_rerank_with_relations()` lines 194-198
- **Who controls:** Hardcoded
- **Good:** Counts both directions within the result set
- **Bad/absent:** Only counts links where BOTH source and target are in the current result set. A well-connected doc that links to documents NOT in results gets no boost from those links
- **Exact values:** Each link adds 1 to both source and target document's connection count

### J. Multi-Query (search_multi)

#### J1. Reciprocal Rank Fusion

- **Where:** `server.py` lines 135, 170-182
- **Who controls:** Hardcoded
- **Good:** Standard RRF merges rankings from multiple queries without score normalization
- **Bad/absent:** Formula: `1 / (k + rank)` where k=60 and rank is 1-based position. Each query runs independently through the full search pipeline (including dedup and reranking). Per-query limit is `limit * 2`
- **Exact values:** k=60 (`_RRF_K = 60`). Per-query fetch: `limit * 2`

#### J2. Query cap

- **Where:** `server.py` line 160
- **Who controls:** Hardcoded
- **Good:** Limits to 5 queries to prevent excessive load
- **Bad/absent:** `queries[:5]` — silently truncates beyond 5
- **Exact values:** Max queries: `5`

#### J3. Result merging

- **Where:** `server.py` lines 171-178
- **Who controls:** Hardcoded
- **Good:** Deduplication by `file_path`, keeps the version with the highest original score
- **Bad/absent:** Final ranking is by RRF score, not BM25 score. The BM25 score stored is from the best-scoring query for that doc, but the RRF score determines order

### K. Configuration

#### K1. `KENSO_DATABASE_URL`

- **Where:** `config.py` lines 22-24
- **Who controls:** Admin
- **Good:** Full control over database location
- **Bad/absent:** Overrides all cascade logic. No validation beyond existence

#### K2. `KENSO_CHUNK_SIZE`

- **Where:** `config.py` line 64
- **Who controls:** Admin
- **Default:** `4000` characters
- **Impact:** Larger chunks = more context per result but fewer, coarser matches. Smaller = more precise but may fragment content

#### K3. `KENSO_CHUNK_OVERLAP`

- **Where:** `config.py` line 65
- **Who controls:** Admin
- **Default:** `0` (disabled)
- **Impact:** Non-zero overlap helps queries that span section boundaries

#### K4. `KENSO_CONTENT_PREVIEW_CHARS`

- **Where:** `config.py` line 63
- **Who controls:** Admin
- **Default:** `200` characters
- **Impact:** Only affects the preview shown in results, not ranking

#### K5. `KENSO_SEARCH_LIMIT_MAX`

- **Where:** `config.py` line 66
- **Who controls:** Admin
- **Default:** `20`
- **Impact:** Caps the maximum results returned per search

#### K6. Content preview — smart preview

- **Where:** `server.py:_smart_preview()` lines 69-87
- **Who controls:** Admin (preview length), hardcoded (logic)
- **Good:** Skips headings, code fences, table rows, empty lines to show prose
- **Bad/absent:** If no prose lines are found, falls back to raw `content[:max_chars]`
- **Exact values:** Skips lines starting with `#`, `` ``` ``, `|`, or empty

---

## Part 2: Impact Ranking

Ranked by estimated impact on whether the right document appears and ranks highly, comparing a well-optimized knowledge base vs. an unoptimized one:

| Rank | Factor | Est. % | Rationale |
|------|--------|--------|-----------|
| 1 | **D1/F1: FTS5 column weights (title=10x)** | 18% | Title match is the single strongest signal. A descriptive title that matches user intent is the #1 determinant of correct ranking |
| 2 | **C1/C10/C11: Chunking by headings + section_path (8x)** | 14% | Good H2 structure creates focused chunks with descriptive section_paths (8x weight). Poor structure -> one giant chunk -> diluted relevance |
| 3 | **B6: Tags in frontmatter (7x weight)** | 12% | Tags are indexed at 7x weight. Adding 3-5 keywords per doc bridges vocabulary gaps (synonyms, abbreviations, alternate terminology) that the tokenizer can't handle |
| 4 | **B3: Title resolution (H1/frontmatter)** | 10% | The document title appears in every chunk's title field (10x weight). A vague or missing H1 weakens all chunks from that doc |
| 5 | **E2: Search cascade (AND -> NEAR -> OR)** | 8% | Determines recall vs. precision tradeoff. The AND stage finds exact matches; falling to OR introduces noise. The cascade design is the core retrieval strategy |
| 6 | **D3: Searchable content formula (aliases, answers, description)** | 7% | Aliases handle synonyms, answers handle question-style queries, description adds summary context — all at 1x weight but covering vocabulary gaps |
| 7 | **B7/B8: Aliases and answers frontmatter** | 6% | Directly addresses the vocabulary mismatch problem. "How do I deploy?" matches a doc with `answers: ["How do I deploy?"]` even if "deploy" isn't in the title |
| 8 | **B4: Category resolution** | 5% | Category filtering (5x weight + WHERE clause) helps when users scope searches. Miscategorized docs appear in wrong category or miss filtering |
| 9 | **D2/H1: Tokenizer (porter + unicode61)** | 5% | Stemming automatically handles inflections (run/running). Diacritics removal handles accented characters. This is foundational but largely invisible |
| 10 | **F3/I1-I3: Relation density reranking** | 4% | 15% boost per connection promotes topic clusters. Significant only when the knowledge base has explicit links |
| 11 | **D5/H3: Compound term expansion** | 3% | Splits camelCase/snake_case queries. Important for codebases but limited (query-side only, no hyphen/dot support) |
| 12 | **C4/C5/C6: Chunk size + sub-splitting** | 3% | Controls granularity. Too large = diluted relevance. Too small = fragmented context. Default 4000 is reasonable for most content |
| 13 | **F2: Deduplication** | 2% | Prevents one doc from taking multiple result slots. More about result quality than finding the right doc |
| 14 | **G1: File path fallback** | 1% | Niche but valuable for exact-path queries. Only triggers when FTS5 returns nothing AND query has `/` or `.` |
| 15 | **A2: Minimum content threshold (50 chars)** | 1% | Prevents noise from stub files. Edge case |
| 16 | **C9: Chunk overlap** | 0.5% | Disabled by default. When enabled, helps cross-boundary queries but adds index bloat |
| 17 | **C2: Preamble chunk (50-char minimum)** | 0.5% | Small impact — overview content may get lost if <50 chars |

**Total: 100%**

---

## Part 3: Gaps

### High Impact

#### Gap 1: No typo tolerance / fuzzy matching

- **What:** FTS5 has no built-in fuzzy matching. A typo like "kuberntes" won't match "kubernetes"
- **How it helps:** Would dramatically improve recall for mistyped queries, especially for technical terms
- **Difficulty:** **Moderate** — Could implement Levenshtein-based query correction against a term dictionary extracted from the index, or use SQLite's `spellfix1` extension. Alternatively, add a trigram index

#### Gap 2: No synonym expansion

- **What:** "k8s" won't match "kubernetes", "JS" won't match "JavaScript" unless tags/aliases are set
- **How it helps:** Reduces reliance on authors manually adding every synonym as a tag
- **Difficulty:** **Moderate** — A synonym table (loaded from config) that expands query terms before FTS5. Could be a simple JSON mapping file

#### Gap 3: No stop word handling

- **What:** Common words like "how", "the", "what", "is" consume FTS5 query slots and dilute relevance
- **How it helps:** "How do I configure logging" -> the meaningful terms are "configure" and "logging", but "how", "do", "I" are also matched
- **Difficulty:** **Trivial** — Filter a stop word list from query terms before building FTS5 queries. SQLite's FTS5 doesn't have built-in stop words

#### Gap 4: No content-side compound term expansion

- **What:** `_expand_compound_word` only runs on queries, not indexed content. Content `orderMatchingEngine` is tokenized as one token
- **How it helps:** Would allow partial-term matches on camelCase/snake_case identifiers in content
- **Difficulty:** **Trivial** — Apply the same expansion during `searchable_content` construction in `ingest_file()`

#### Gap 5: No hyphen/dot compound splitting

- **What:** `_expand_compound_word` handles `_` and camelCase but not `foo-bar` or `com.example.Class`
- **How it helps:** Hyphenated terms are common in docs (e.g., "CI/CD", "pre-commit", "real-time")
- **Difficulty:** **Trivial** — Add hyphen and dot splitting to `_expand_compound_word`

### Medium Impact

#### Gap 6: No query term boosting / field-specific queries

- **What:** All query terms are treated equally. No way to say "this term MUST be in the title"
- **How it helps:** Users searching for a specific doc by name could get much better precision
- **Difficulty:** **Moderate** — Could detect patterns (e.g., quoted terms) and route to `title:` or `tags:` column-specific FTS5 queries

#### Gap 7: No document freshness signal

- **What:** `created_at` and `updated_at` are stored but never used in ranking
- **How it helps:** Recently updated docs are often more relevant, especially for evolving codebases
- **Difficulty:** **Trivial** — Add a recency decay factor in `_rerank_with_relations()` or a new reranking step

#### Gap 8: No `.kensoignore` or exclusion patterns

- **What:** All `.md` files under the root are ingested, including drafts, templates, changelogs
- **How it helps:** Prevents noise from non-documentation files polluting results
- **Difficulty:** **Trivial** — Read a `.kensoignore` file (gitignore-style patterns) during `scan_files()`

#### Gap 9: No frontmatter `priority` or `weight` field

- **What:** Authors can't signal that certain docs are canonical/authoritative
- **How it helps:** A "Getting Started" guide could be boosted over an obscure troubleshooting doc
- **Difficulty:** **Trivial** — Read a `priority` frontmatter field and apply a multiplier during reranking

#### Gap 10: No snippet/highlight for the winning match

- **What:** Snippets come from `searchable_content` (column 4) only, not from the highest-weighted matching column
- **How it helps:** If a title match wins, the snippet should show why, not some random content passage
- **Difficulty:** **Moderate** — Would need to run multiple snippet extractions or use custom highlighting

### Lower Impact

#### Gap 11: No deleted file cleanup

- **What:** If a file is removed from disk, its chunks and links remain in the database
- **How it helps:** Stale docs don't appear in results after files are deleted
- **Difficulty:** **Trivial** — During ingestion, delete DB entries for paths no longer on disk

#### Gap 12: No BM25 parameter tuning

- **What:** Uses SQLite default k1=1.2, b=0.75. No experimentation with alternatives
- **How it helps:** Tuning b (length normalization) could help with mixed chunk sizes; tuning k1 could adjust term frequency saturation
- **Difficulty:** **Complex** — FTS5 doesn't expose k1/b directly; would require a custom ranking function or switching to a different search backend

#### Gap 13: No usage analytics / click-through feedback

- **What:** No mechanism to learn which results users actually find useful
- **How it helps:** Could feed into a relevance model over time
- **Difficulty:** **Complex** — Would need logging, storage, and a feedback-weighted reranking layer

#### Gap 14: No file type support beyond `.md`

- **What:** `.mdx`, `.txt`, `.rst`, `.adoc` files are ignored
- **How it helps:** Broader coverage for knowledge bases that use multiple formats
- **Difficulty:** **Trivial** for `.mdx`/`.txt` (same parser), **Moderate** for `.rst`/`.adoc` (different parsers)

#### Gap 15: Preamble content loss when < 50 chars

- **What:** Content before first H2 that's under 50 characters is silently discarded
- **How it helps:** Short intros ("This guide covers X and Y.") could still be valuable context
- **Difficulty:** **Trivial** — Merge preamble into the first section chunk instead of discarding
