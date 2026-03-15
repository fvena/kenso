# How kenso Works

This guide explains what happens inside kenso when you ingest documents and when an LLM searches them. It's written to help you understand *why* kenso returns the results it does — and what you can tune if it doesn't.

Each section links to the relevant source file so you can follow along in the code.

## The big picture

kenso has two phases: **ingest** (offline, when you run `kenso ingest`) and **search** (online, when the LLM calls a tool). Understanding both helps you write better documents and debug retrieval issues.

```
           INGEST                                    SEARCH
           ──────                                    ──────

         .md files                                  LLM query
              │                                         │
              ▼                                         ▼
      parse frontmatter                         build FTS5 cascade
              │                                  AND → NEAR → OR
              ▼                                         │
      split into chunks                                 ▼
      (by H2 headings)                          fetch 3× candidates
              │                                         │
              ▼                                         ▼
     build searchable_content                      deduplicate
     (chunk + aliases + tags)                   (1 chunk per doc)
              │                                         │
              ▼                                         ▼
      index in SQLite FTS5                      re-rank by relations
      (5 weighted columns)                              │
              │                                         ▼
              ▼                                  enrich metadata
      extract relates_to                                │
  (typed bidirectional links)                           ▼
                                               return top-K results
```

## Ingestion

> Source: `src/kenso/ingest.py` → `ingest_path()`

### 1. Scanning and hashing

kenso recursively finds all `.md` files in the given directory. For each file, it computes a SHA-256 hash of the entire raw text (including frontmatter). If the hash matches what's already in the database, the file is skipped. This is why re-running `kenso ingest` is fast — only changed files get re-processed.

Files under 50 characters are skipped entirely (they have too little content to be useful).

### 2. Frontmatter parsing

> Source: `src/kenso/ingest.py` → `parse_frontmatter()`

kenso reads the YAML block between `---` markers at the top of each file. If `pyyaml` is installed, it uses `yaml.safe_load()` for full YAML support (lists, nested dicts). Otherwise, it falls back to a simple key-value parser.

The fields kenso understands:

| Field | Used for |
|-------|----------|
| `title` | Chunk title, indexed at highest weight |
| `category` | Stored as metadata, indexed, used for filtering |
| `tags` | Indexed at high weight, bridges vocabulary gaps |
| `aliases` | Injected into searchable content |
| `answers` | Injected into searchable content |
| `description` | Injected into searchable content |
| `audience` | Stored as metadata |
| `relates_to` | Builds the document graph |

If `title` is missing, kenso uses the first H1 heading. If `category` is missing, it uses the parent directory name.

### 3. Chunking

> Source: `src/kenso/ingest.py` → `chunk_by_headings()`

A document is split into chunks at H2 (`##`) boundaries. Each H2 section becomes one chunk. This matters because each chunk is retrieved independently — the LLM doesn't see the whole document unless it explicitly requests it with `get_doc`.

Three special cases:

**Preamble.** Everything before the first H2 becomes a dedicated chunk titled "Document Title — Overview". This is often the most valuable chunk because it contains the summary, synonyms, and context that match broad queries.

**Oversized sections.** If an H2 section exceeds `KENSO_CHUNK_SIZE` (default 4,000 chars), it gets sub-split at H3/H4 boundaries. If it's still too large, kenso splits at paragraph boundaries — but never inside a fenced code block or a table.

**Chunk titles.** Each chunk gets a full hierarchical title: "Document Title > Section Title". This is indexed at 10× weight, so a specific heading like "Settlement Lifecycle > Failed Trade Handling" is much easier to find than a generic "Handling".

### 4. Building searchable content

> Source: `src/kenso/ingest.py` → `_build_metadata_preamble()`

For each chunk, kenso builds a `searchable_content` field that combines the chunk's actual text with metadata from frontmatter:

```
searchable_content = chunk text + aliases + answers + description + tags as keywords
```

This is the field indexed by FTS5 at 1× weight. The original `content` field stays clean — it's what the LLM reads when it calls `get_doc`.

Why separate them? Because `aliases` like "liquidación de operaciones" should be searchable but shouldn't appear in the document content. The LLM searches `searchable_content` but reads `content`.

### 5. FTS5 indexing

> Source: `src/kenso/schema.py` → `get_schema()`

Each chunk gets inserted into a SQLite FTS5 virtual table with five indexed columns. The weight determines how much a keyword match in that column influences the BM25 score:

| Column | Weight | What it contains |
|--------|--------|------------------|
| `title` | 10× | "Document Title > Section Title" |
| `section_path` | 8× | Full heading hierarchy |
| `tags` | 7× | "settlement, clearing, T+2, DVP" |
| `category` | 5× | "post-trade" |
| `searchable_content` | 1× | Chunk text + aliases + answers + keywords |

A match in the title is worth 10× a match in the body. This is why specific, keyword-rich headings dramatically improve retrieval.

The tokenizer is `porter unicode61 remove_diacritics 2`, which means:
- Porter stemming: "settlements" and "settlement" match
- Unicode61: handles accented characters (liquidación → liquidacion)
- Diacritics removal: "café" matches "cafe"

FTS5 stays in sync with the main table via SQLite triggers — every insert, update, or delete on `chunks` automatically updates the FTS index.

### 6. Link extraction

> Source: `src/kenso/ingest.py` → `extract_relates_to()`

kenso reads the `relates_to` field from frontmatter and inserts bidirectional links into the `links` table. Links can be simple (just a path) or typed (path + relation):

```yaml
# Simple
relates_to:
  - order-management/matching-engine.md

# Typed
relates_to:
  - path: order-management/matching-engine.md
    relation: receives_from
```

These links are stored as `(source_path, target_path, relation_type)` and are used in two places: re-ranking search results and powering the `get_related` tool.

## Search

> Source: `src/kenso/backend.py` → `search()`

When the LLM calls `search_docs("settlement failed trade")`, five things happen in sequence.

### Step 1: Build the query cascade

> Source: `src/kenso/backend.py` → `_to_fts5_queries()`

kenso doesn't just throw the query at FTS5 as-is. It builds three versions of increasing broadness:

```
1. AND:      settlement AND failed AND trade
2. NEAR/10:  NEAR(settlement failed trade, 10)
3. OR:       settlement OR failed OR trade
```

It tries them in order. The first version that returns at least 3 results wins. This means:
- If all three words appear together in a chunk, you get precise results (AND).
- If they appear close together but not all in the same phrase, you still find them (NEAR).
- If only one word matches, you get something rather than nothing (OR).

This cascade is why kenso handles both precise queries ("FIX protocol integration") and vague queries ("how do members connect") well.

### Step 2: Fetch extra candidates

> Source: `src/kenso/backend.py` → `_search_keyword()`

kenso fetches 3× the requested limit. If the LLM asks for 5 results, kenso fetches 15 candidates. This headroom is needed because the next two steps (dedup and re-ranking) will filter and reorder them.

Each candidate comes back with a BM25 score, a title, a content preview (first ~200 chars, skipping headings and code fences), and an FTS5 snippet with matched terms in `<mark>` tags.

### Step 3: Deduplicate

> Source: `src/kenso/backend.py` → `_deduplicate()`

A single document can produce multiple chunks, and multiple chunks from the same document might match the query. Without dedup, the top 5 results could be 5 chunks from the same file — not useful.

kenso keeps only the highest-scoring chunk per document. If chunks 2, 7, and 12 all come from `settlement.md`, only the best one survives.

### Step 4: Re-rank by relations

> Source: `src/kenso/backend.py` → `_rerank_with_relations()`

After dedup, kenso checks the `links` table to see which results are connected to each other. If `settlement.md` and `cnmv-reporting.md` are both in the result set and they link to each other, both get a score boost.

The formula is: `boosted_score = original_score × (1 + 0.15 × connections)`. A document with 2 connections to other results gets a 30% boost.

This biases results toward clusters of related documents — which is usually what the LLM needs. If you ask about "CNMV settlement reporting", you want the settlement doc *and* the CNMV doc, not two random matches.

### Step 5: Enrich metadata

> Source: `src/kenso/backend.py` → `_enrich_metadata()`

Finally, kenso adds `tags`, `category`, and `related_count` to each result. This metadata helps the LLM decide which documents to read in full and which related documents to explore with `get_related`.

## Multi-query search

> Source: `src/kenso/server.py` → `search_multi()`

`search_multi` is designed for complex questions that span multiple concepts. The LLM decomposes a question like "How does CNMV regulation affect the settlement process?" into separate queries:

```python
search_multi(["CNMV regulation reporting", "settlement process compliance"])
```

Each query runs through the full search pipeline independently. Results are then merged using **Reciprocal Rank Fusion (RRF)**:

```
score = sum(1 / (60 + rank_in_query))
```

A document that appears at rank 1 in both queries gets `1/61 + 1/61 = 0.033`. A document at rank 1 in one and rank 5 in another gets `1/61 + 1/65 = 0.032`. Documents that appear in multiple queries naturally float to the top.

After merging, the combined results go through dedup and enrichment (same as regular search). The LLM gets a diverse set of documents that collectively answer the multi-faceted question.

## Document graph traversal

> Source: `src/kenso/backend.py` → `get_related()`

The `get_related` tool lets the LLM explore connections between documents. It performs a breadth-first traversal of the links table.

**Depth 1** returns direct neighbors — documents that link to or from the given path:

```
get_related("settlement.md", depth=1)
→ matching-engine.md (receives_from, outgoing)
→ cnmv-reporting.md  (triggers, outgoing)
```

**Depth 2** also traverses neighbors of neighbors:

```
get_related("settlement.md", depth=2)
→ matching-engine.md    (depth 1)
→ cnmv-reporting.md     (depth 1)
→ platform-overview.md  (depth 2, via matching-engine)
→ market-surveillance.md (depth 2, via cnmv-reporting)
→ ... 7 documents total
```

The traversal uses a visited set to prevent cycles but collects all link records (a document can appear with multiple relation types). The `relation_type` parameter filters results: `get_related("settlement.md", relation_type="triggers")` returns only documents connected by a "triggers" relation.

The depth is capped at 3 to prevent explosion in highly connected graphs.

## Putting it all together

A typical LLM interaction with kenso looks like this:

```
User: "What happens when a settlement fails?"

LLM:
  1. search_docs("settlement failure handling")
     → settlement.md (score 15.2), cnmv-reporting.md (score 8.1)

  2. get_doc("settlement.md")
     → reads the full document, finds the "Failed Settlement Handling" section

  3. get_related("settlement.md", depth=1)
     → discovers cnmv-reporting.md is connected (relation: triggers)

  4. Synthesizes an answer citing both documents
```

The LLM uses search to find the right documents, `get_doc` to read them, and `get_related` to discover context it wouldn't have found by keyword alone. Three tool calls, grounded answer.

## What to check when retrieval isn't working

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Query returns no results | Terms don't appear in any indexed content | Add `aliases` or `tags` in frontmatter with the terms users would search |
| Right document but wrong section | The best chunk doesn't contain the key terms | Repeat canonical terms in each H2 section, not just the first mention |
| Too many results from one document | Dedup not helping | Check that each H2 section is self-contained with a specific heading |
| Related documents not connected | Missing `relates_to` in frontmatter | Add `relates_to` links between the documents you want the LLM to discover together |
| Score is low despite correct result | Terms only appear in the body (1× weight) | Move key terms into the title (10×), tags (7×), or heading (8×) |

You can debug with `kenso search` from the terminal to see scores and highlights before connecting to an editor.
