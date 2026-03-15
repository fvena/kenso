# Write docs your agent actually finds

This guide covers how to structure and write Markdown documents to maximize retrieval quality. Every recommendation here is grounded in how kenso's search pipeline actually works — not general SEO advice.

Unlike embedding-based RAG, kenso uses keyword search (BM25) — which means *you* control what gets found by writing better documents, not by tweaking embedding models. That's the trade-off: more control, but you need to know how to use it.

## What impacts retrieval quality

Every factor in the search pipeline contributes to whether the right document appears in results. This table ranks them by impact — if you can only improve one thing, start at the top.

| Rank | Factor | Impact | Who controls it |
|------|--------|--------|-----------------|
| 1 | Document title (H1 or frontmatter `title`) | 18% | Author |
| 2 | H2 structure and section headings | 14% | Author |
| 3 | Tags with synonyms and acronyms | 12% | Author |
| 4 | Title specificity across all chunks | 10% | Author |
| 5 | Search cascade (AND → NEAR → OR) | 8% | Hardcoded |
| 6 | Aliases, answers, and description | 7% | Author |
| 7 | Vocabulary bridging (aliases + answers) | 6% | Author |
| 8 | Category assignment | 5% | Author / directory |
| 9 | Tokenizer (Porter stemmer + unicode61) | 5% | Hardcoded |
| 10 | Relation links (`relates_to`) | 4% | Author |
| 11 | Compound term expansion | 3% | Hardcoded |
| 12 | Chunk size configuration | 3% | Admin |
| 13 | Deduplication | 2% | Hardcoded |
| 14 | File path fallback | 1% | Hardcoded |
| 15 | Minimum content threshold | 1% | Hardcoded |
| 16 | Chunk overlap | 0.5% | Admin |
| 17 | Preamble chunk | 0.5% | Author |

**67% of retrieval quality is directly controlled by the document author.** The title, headings, tags, aliases, and answers are the levers you have. The remaining 33% is handled by kenso's search pipeline.

## How kenso sees your documents

Understanding the pipeline helps you write better docs.

1. **Frontmatter is parsed** — `title`, `category`, `tags` are stored as metadata. `aliases`, `answers`, `description` are injected into the searchable index.
2. **Content before the first H2 becomes a preamble chunk** — titled "Document Title — Overview". This is the highest-value chunk for vocabulary bridging.
3. **Each H2 section becomes a chunk** — the H2 heading becomes the chunk title, indexed at 10× weight. Oversized sections are sub-split at H3/H4.
4. **Each chunk is retrieved independently** — a chunk must be self-contained. If it references "the engine" without saying which engine, it's a weak retrieval target.
5. **Search uses a weighted index** — title (10×), section_path (8×), tags (7×), category (5×), content (1×). A keyword match in the title matters 10× more than in the body.

### What the tokenizer already handles

kenso's FTS5 tokenizer handles several vocabulary variations automatically — you don't need to add these as tags:

- **Porter stemming** — "configuring", "configuration", "configured" all match. Same for "deploy" / "deployment" / "deploying".
- **Diacritics** — "José" matches "jose", "café" matches "cafe" (Latin script only).
- **Case folding** — "API" matches "api", "OAuth" matches "oauth".
- **Compound terms** — `orderMatchingEngine` in a query is expanded to also search "order", "matching", "engine" separately. Same for `snake_case`, `hyphen-ated`, and `dotted.terms`.

What the tokenizer does NOT handle — these need explicit tags or aliases:

- **Abbreviations** — "k8s" won't match "kubernetes", "JS" won't match "JavaScript".
- **True synonyms** — "login" won't match "authentication", "deploy" won't match "ship".
- **Translations** — "settlement" won't match "liquidación".
- **Domain jargon** — "the book" won't match "order book" if that's how your team talks.

## Frontmatter

Every document should have frontmatter. The more fields you fill, the more findable the document becomes.

### Required fields

```yaml
---
title: Settlement Lifecycle for Equity Trades
category: post-trade
tags: settlement, clearing, T+2, DVP, CNMV
---
```

**title** — The single most important field (18% of retrieval quality). Indexed at 10× weight and inherited by every chunk in the document. Be specific and include the key terms someone would search for. "Settlement Lifecycle for Equity Trades" beats "Settlement" or "Lifecycle".

**category** — Indexed at 5× weight. Use a controlled vocabulary across your knowledge base (10–30 categories max). Agents can filter search by category. If not set in frontmatter, kenso uses the parent directory name (e.g., `docs/post-trade/settlement.md` → category `post-trade`). If the file is at the root of the ingested path, the fallback is `general`. Category comparison is case-sensitive — use consistent casing. Frontmatter always takes precedence.

**tags** — Indexed at 7× weight (12% of retrieval quality). Include synonyms, acronyms, and alternative terms that don't appear in the title. If the document is about "KYC verification", tag it with `KYC, AML, know-your-customer, compliance, onboarding`. Tags are the cheapest way to close vocabulary gaps.

Since the tokenizer already handles inflections (deploy/deployment) and diacritics (José/jose), focus your tags on terms the tokenizer can't infer: abbreviations, acronyms, true synonyms, and domain-specific jargon.

### Recommended fields

```yaml
aliases:
  - trade settlement
  - post-trade processing
  - liquidación de operaciones
answers:
  - How are equity trades settled on the platform?
  - What is the T+2 settlement cycle?
  - What happens when a settlement fails?
relates_to:
  - path: order-management/matching-engine.md
    relation: receives_from
  - path: compliance/cnmv-reporting.md
    relation: triggers
```

**aliases** — Alternative names injected directly into the searchable index as "Also known as: ...". A search for "login" will match this document even if "login" never appears in the body. Use them for: translations, informal names, abbreviations, and terms users might search that don't appear in the body. This is the most effective tool against vocabulary mismatch.

**answers** — Questions this document answers, injected as "Questions this document answers: ...". When an LLM generates a search query from a user's question, the overlap with pre-written questions is very high. Write 2–5 questions in the same language and style your users would ask.

**relates_to** — Links to related documents. These build a navigable graph that agents can traverse. Each connection to another document in the result set adds a 15% score boost during re-ranking. Use typed relations for richer semantics (see [Relation types](#relation-types)).

### Optional fields

```yaml
description: >
  Covers the complete settlement lifecycle from trade execution
  to final DVP, including T+2 cycles, failed settlement handling,
  and CNMV reporting requirements.
```

**description** — A 1–3 sentence summary injected into the searchable index (no label prefix, appended as plain text). Useful when the document body is highly technical but users search with general terms.

## Document structure

### The preamble matters

Everything between the H1 and the first H2 becomes a dedicated "Overview" chunk (minimum 50 characters). This is the ideal place for:

- A dense summary of what the document covers
- Synonyms and alternative terminology
- Scope statement (what's included and what's not)

```markdown
# Settlement Lifecycle for Equity Trades

The settlement process manages the final exchange of securities and cash
after a trade is executed on the multilateral trading facility (MTF).
This document covers the complete settlement lifecycle, T+2 cycles,
central counterparty clearing, failed trade handling, and CNMV
regulatory requirements for settlement reporting.

## Settlement Phases

...
```

Without this preamble, the document loses its best chunk for broad queries. If you write nothing before the first H2, the Overview chunk is empty. If the preamble is shorter than 50 characters, it gets merged into the first section chunk rather than becoming its own overview.

### Headings are retrieval targets

H2 headings become chunk titles, indexed at 10× weight. The full path (document title + section title) is indexed at 8× as `section_path`. Together, these account for 14% of retrieval quality.

```markdown
## Settlement Lifecycle Phases for Equity Trades    ← specific, rich in keywords
```

```markdown
## Phases                                           ← generic, matches everything
```

A heading like "Configuration" appears in dozens of documents. "API Gateway Rate Limiting Configuration" appears in exactly one. The more specific the heading, the more precise the retrieval.

Sections with content under 20 characters (just a heading with no real content) are silently dropped from the index.

### Lead with the key sentence

The first ~200 characters of each section become the preview that helps the LLM decide whether to request the full document. Put the most informative sentence first.

```markdown
## Failed Settlement Handling

When a settlement fails due to insufficient securities or cash shortfall,
the system triggers an automatic buy-in procedure and reports to CNMV
within 24 hours.
```

Not:

```markdown
## Failed Settlement Handling

This section describes what happens in various failure scenarios
during the settlement process. There are several types of failures
that can occur...
```

### Repeat canonical terms

Each chunk is retrieved independently. If chunk 3 says "the engine processes incoming orders", it won't match a search for "matching engine". Say "the order matching engine processes incoming orders".

Rules:

- Use the full term at least once per section, not just in the first mention.
- Avoid pronouns ("it", "this", "the system") when the section might be read without context.
- If an acronym is important, write it out once per section: "CNMV (Comisión Nacional del Mercado de Valores)".

### Optimal section size

kenso's default chunk size is 4,000 characters (configurable via `KENSO_CHUNK_SIZE`). Sections that are too long get sub-split at H3/H4, which can break context. Sections that are too short dilute the keyword signal.

| Size | Effect |
|------|--------|
| < 100 chars | Too small — low BM25 signal, likely noise |
| 200–800 chars | Good for focused, single-concept sections |
| 800–2,000 chars | Ideal for most technical content |
| 2,000–4,000 chars | Acceptable if the topic is cohesive |
| > 4,000 chars | Will be sub-split — consider breaking into H3 subsections yourself |

If you control the split, you control the chunk boundaries. If kenso splits for you, the boundary might land in an awkward place.

Code blocks and tables are protected from splitting — they will never be broken mid-block. Paragraph boundaries (`\n\n`) are used as safe split points when sub-splitting is needed.

## Relation types

Use consistent relation types across your knowledge base. These enable agents to ask graph-aware questions like "what feeds into settlement?" or "what does the matching engine trigger?".

Each link between documents that both appear in a result set adds a 15% boost to both documents' scores. This means well-connected documents in a topic cluster reinforce each other's ranking.

```yaml
relates_to:
  - path: order-management/matching-engine.md
    relation: receives_from
```

### Recommended vocabulary

| Relation | Meaning | Example |
|----------|---------|---------|
| `feeds_into` | Upstream data flow | matching-engine → settlement |
| `receives_from` | Downstream dependency | settlement ← matching-engine |
| `triggers` | Causal relationship | settlement → cnmv-reporting |
| `contains` | Parent-child hierarchy | platform-overview → api-gateway |
| `part_of` | Inverse of contains | api-gateway → platform-overview |
| `monitors` | Observational | surveillance → matching-engine |
| `implements` | Spec to implementation | adr-003 → event-sourcing |
| `required_by` | Regulatory dependency | onboarding → cnmv-reporting |
| `derived_from` | Computed from | liquidity-metrics → market-data-feed |

You can use any string as a relation type — these are suggestions, not constraints. The value is in consistency: pick a vocabulary and use it everywhere.

### How many links?

- 2–5 links per document is the sweet spot.
- Link to the most important related documents, not every tangentially related one.
- The agent can traverse up to depth 3 (neighbors of neighbors of neighbors), so you don't need to link everything directly.

### Simple format

If you don't need typed relations, a simple list works:

```yaml
relates_to:
  - order-management/matching-engine.md
  - compliance/cnmv-reporting.md
```

All links get the default type `related`. Glob patterns (`*`, `?`) in paths are not supported and will be silently ignored.

## Directory organization

kenso infers `category` from the parent directory when frontmatter doesn't specify one. A clean directory structure gives you automatic categorization.

```
docs/
├── domain/
│   ├── orders/            → category: orders
│   ├── operations/        → category: operations
│   └── entities/          → category: entities
├── architecture/
│   ├── backend/           → category: backend
│   ├── frontend/          → category: frontend
│   └── integrations/      → category: integrations
├── flows/                 → category: flows
├── guides/                → category: guides
└── decisions/             → category: decisions
```

This is an example — your directory structure should reflect the natural taxonomy of your team and domain. The only rule is: keep it shallow. One level of nesting is enough for category inference. Deeper nesting doesn't add retrieval value.

**Precedence:** frontmatter `category` always wins. If not set, kenso uses the parent directory name. Files at the root of the ingested path get the category `general`.

**File names matter as a last resort.** If a document has no H1 and no frontmatter `title`, the filename stem becomes the document title (e.g., `my-guide.md` → "my-guide"). Use descriptive filenames even if you always set frontmatter titles.

## Vocabulary bridging

The biggest limitation of keyword search (BM25) is vocabulary mismatch: the user searches "login" but the document says "authentication". kenso provides multiple tools to bridge this gap, ranked by effectiveness:

### 1. Aliases (most effective)

```yaml
aliases:
  - login system
  - access control
  - autenticación
```

Aliases are injected directly into the searchable index. A search for "login" will match this document even if "login" never appears in the body.

### 2. Tags

```yaml
tags: authentication, OAuth2, JWT, login, access-control
```

Tags are indexed at 7× weight. Include common synonyms, acronyms, and informal terms. Remember: the tokenizer already handles inflections (authenticate/authentication), so focus on terms that are genuinely different words.

### 3. Preamble with synonyms

```markdown
# API Gateway and Authentication

The API gateway (also known as: login system, access control layer,
API security gateway) handles all external authentication...
```

Natural text in the preamble that includes alternative terms. This is indexed as the Overview chunk.

### 4. Answers

```yaml
answers:
  - How do users log in to the platform?
  - What are the API rate limits?
```

Matches question-style queries that LLMs typically generate.

### 5. Synonym file (project-level)

For abbreviations and domain terms that recur across many documents, a project-level synonym file avoids repeating the same tags everywhere:

```yaml
# .kenso/synonyms.yml
groups:
  - [kubernetes, k8s, kube]
  - [javascript, js]
  - [database, db]
  - [pull request, pr, merge request, mr]
```

When any term in a group appears in a query, kenso expands it to search for all variants. This is configured once per project, not per document.

### When to use which

| Scenario | Best tool |
|----------|-----------|
| The concept has a well-known alternative name | `aliases` |
| Users might search with informal/abbreviated terms | `tags` |
| The document covers a concept known by different names in different contexts | preamble with synonyms |
| Users will ask questions about this topic | `answers` |
| Multiple languages | `aliases` (one per language) |
| Abbreviations shared across many documents | synonym file |

## Complete example

A well-structured document applying all the principles above:

```markdown
---
title: API Gateway Rate Limiting and Throttling
category: architecture
tags: rate-limit, throttle, API, gateway, quota, 429, backpressure
aliases:
  - API throttling
  - request limiting
  - limitación de peticiones
answers:
  - How does the API rate limiter work?
  - What happens when a client exceeds the rate limit?
  - How do I configure rate limits per endpoint?
description: >
  Covers the token-bucket rate limiter in the API gateway, including
  per-client quotas, endpoint overrides, and 429 response handling.
relates_to:
  - path: architecture/api-gateway.md
    relation: part_of
  - path: guides/client-integration.md
    relation: feeds_into
  - path: monitoring/api-alerts.md
    relation: triggers
---

# API Gateway Rate Limiting and Throttling

The API gateway enforces per-client rate limits using a token-bucket
algorithm. Every authenticated client receives a default quota of
1,000 requests per minute. When a client exceeds its quota, the
gateway returns HTTP 429 with a `Retry-After` header.

This document covers the token-bucket implementation, per-endpoint
overrides, burst handling, and monitoring integration.

## Token-Bucket Algorithm

The API gateway rate limiter uses a token-bucket algorithm with
configurable refill rate. Each client gets an independent bucket
identified by API key. Tokens are consumed on each request and
refilled at a constant rate (default: 16.6 tokens/second for a
1,000/minute quota).

When the bucket is empty, the API gateway rate limiter rejects the
request with HTTP 429 and includes a `Retry-After` header indicating
when the next token will be available.

## Per-Endpoint Rate Limit Overrides

The API gateway rate limiter supports per-endpoint overrides via
the `rate_limits` configuration map. Endpoints not listed in the
map inherit the default client quota...
```

Note how the document:
- Has a keyword-rich title and heading (not "Rate Limiting" alone)
- Includes a preamble that summarizes scope and key concepts
- Repeats "API gateway rate limiter" in each section instead of "it"
- Uses aliases for translations and informal terms
- Starts each section with the most informative sentence

## Re-indexing after changes

kenso tracks file changes via SHA-256 hash of the entire raw text, including frontmatter. If you change any part of the file — even just adding a tag — `kenso ingest` will detect the change and re-index the file. Any whitespace or metadata change triggers a full re-index of that file.

## Checklist

Before committing a new document, verify:

- [ ] Title is specific and keyword-rich (18% of retrieval quality)
- [ ] Category is set (or directory structure provides it)
- [ ] Tags include synonyms and acronyms not in the title — skip inflections the tokenizer already handles
- [ ] There is a preamble paragraph before the first H2 (at least 50 characters)
- [ ] H2 headings are descriptive, not generic (14% of retrieval quality)
- [ ] Each section starts with a key sentence, not boilerplate
- [ ] Canonical terms are repeated per section (no dangling pronouns)
- [ ] `relates_to` links the 2–5 most important related documents
- [ ] Aliases cover vocabulary gaps (translations, informal names, abbreviations)
- [ ] No section exceeds 4,000 characters without H3 sub-sections
- [ ] Sections with content under 20 characters are removed or expanded
