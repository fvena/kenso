# Kenso — Roadmap

Reference: [VISION.md](./VISION.md)

---

## Current state

Kenso works as a search tool. The full ingest → search → retrieve pipeline is implemented
and tested. Users install kenso, run `kenso ingest`, configure MCP in their editor, and
query their docs through the LLM.

| Implemented | Status |
|-------------|--------|
| `kenso ingest` (scan, hash, chunk, FTS5 index, relates_to) | ✓ |
| `kenso search` (FTS5 cascade, dedup, relation re-ranking) | ✓ |
| `kenso lint` (18 rules, score, summary/detail/JSON) | ✓ |
| `kenso stats` | ✓ |
| `kenso serve` (MCP stdio + streamable-http) | ✓ |
| MCP tools (search_docs, search_multi, get_doc, get_related) | ✓ |
| Writing guide | ✓ |
| Eval harness (36 queries, 10 categories) | ✓ |

What's missing: the slash commands, the install system, the generation/optimization
workflows, the document templates, and the CI/CD integration.

---

## Phase 1 — CLI foundations

**Goal:** Extend the existing CLI with the minimum capabilities that Phase 2
(first slash command) needs. No user-facing changes in workflow — kenso still
works exactly as before. This phase builds infrastructure.

Tasks moved to later phases:
- `kenso status` → moved to Phase 4 (only needed by `/kenso:update`)
- `kenso apply` → moved to Phase 3 (only needed by cross-analysis)

### 1.1 Lint integrated into ingest

`kenso ingest` currently indexes and reports what it processed. After this
change, it also runs lint and reports quality metrics in the same output.

```
kenso ingest ./docs

Indexed: 47 files (3 new, 2 modified, 42 unchanged)

Quality Score: 62/100
  Frontmatter completeness:  71%
  Heading specificity:        58%
  Cross-linking coverage:     43%
  Tag consistency:            78%

14 files with issues. Run `kenso lint --detail` for specifics.
```

Lint always runs — no opt-out flag. If it turns out to be slow on very large
KBs, reconsider later.

### 1.2 JSON output for ingest

`kenso ingest` gets a `--json` flag that outputs structured data instead of
human-readable text. This is what slash commands will parse.

```bash
kenso ingest ./docs --json
```

`kenso lint --json` already exists. Verify it covers all fields that the
slash commands will need (per-file scores, individual violations, global
breakdown by category).

### 1.3 Install command

```bash
kenso install              # → .agents/skills/ (universal standard)
kenso install --claude     # → .claude/commands/kenso/ + .claude/skills/ + settings.json
kenso install --codex      # → .codex/skills/ (legacy)
```

Slash commands in `.claude/commands/kenso/` are thin wrappers (~5 lines) that
delegate to the skill in `.claude/skills/`.

Skills use the Agent Skills standard (SKILL.md with YAML frontmatter). No format
conversion needed between runtimes.

On first run, creates the directory structure. On subsequent runs, updates files
(overwrites skill and command files, preserves user modifications in AGENTS.md/CLAUDE.md).

Implementation prompts for all three tasks are in `phase-1-prompts.md`.

**Deliverable:** kenso CLI has the infrastructure that slash commands need.
The user doesn't see any workflow change yet, but the building blocks are in place.

---

## Phase 2 — First slash command: `/kenso:ask`

**Goal:** Prove the full stack works end-to-end — from `kenso install` through
command execution to useful output. `/kenso:ask` is the simplest command because
it doesn't generate or modify files, only reads.

### 2.1 Extend kenso search CLI

`kenso search` currently only takes a query string and returns human-readable
output. The slash commands need structured output with filtering:

```bash
kenso search "settlement failed trade" --json --limit 5 --category rules
```

Add `--json`, `--limit`, and `--category` flags. The JSON output should match
the schema that `search_docs` MCP tool already returns, ensuring consistency
between CLI and MCP interfaces.

### 2.2 Write the kenso:ask canonical command

Create the first skill at `skills/kenso-ask/SKILL.md`. This is the canonical
command — a single-file skill (~80 lines) with no workflow or agent dependencies.
It runs entirely in the LLM's main context. The SKILL.md is the universal format:
the same file works in Claude Code (via thin slash command wrapper), Codex, Cursor,
Copilot, and Gemini CLI.

Also create the canonical directory structure in the repo (`skills/`,
`workflows/`, `agents/`, `references/`, `templates/`) even if most are
empty — this establishes the convention for later phases.

See [COMMANDS.md](./COMMANDS.md) § `/kenso:ask` for the full spec.

### 2.3 End-to-end validation

Manual test:

1. Install kenso in a project with existing docs
2. Run `kenso ingest ./docs`
3. Run `kenso install --claude` (or `--codex`)
4. Open Claude Code, type `/kenso:ask How does settlement work?`
5. Verify the agent invokes `kenso search`, reads results, synthesizes answer

Implementation prompts for all tasks are in `phase-2-prompts.md`.

Implementation prompts for all tasks are in `phase-2-prompts.md`.

**Deliverable:** A user can install kenso, run two commands (`ingest` + `install`),
and start asking questions about their docs from within Claude Code or Codex.
The slash command infrastructure is proven.

---

## Phase 3 — `/kenso:init`: generate + optimize + index

**Goal:** The flagship command. A user with a codebase and no documentation (or
existing docs that aren't optimized) runs `/kenso:init` and gets a complete,
indexed, high-quality knowledge base.

This is the largest phase. It introduces all four layers (command → workflow →
agent → tool) and the document templates.

### 3.1 Apply command (moved from Phase 1)

```bash
kenso apply <plan.yml>
```

Reads a YAML plan (produced by the cross-analysis agent) and applies frontmatter
changes to the specified files. Operations: add `relates_to` entries, add/normalize
tags, normalize categories.

This is an internal command — the user never runs it directly. The optimization
workflow generates the plan, the agent validates it, and `kenso apply` executes it
deterministically.

### 3.2 Document templates

Create the template files that the generation agents use:

```
templates/
  codebase/
    architecture.md     ← modules, layers, boundaries
    structure.md        ← directory tree with annotations
    stack.md            ← languages, frameworks, dependencies
    conventions.md      ← naming, patterns, do/don't
    testing.md          ← test framework, patterns, helpers
    integrations.md     ← external services, config
    concerns.md         ← tech debt, fragile areas
  domain/
    project.md          ← project identity, context
    actors.md           ← roles and capabilities
    domain-model.md     ← entities and relationships
    workflows.md        ← main business flows
  knowledge/
    entity.md           ← lifecycle, states, rules, implementation
    action.md           ← preconditions, effects, failure modes
    workflow.md         ← multi-step flow with branching
    rules.md            ← business rules with BR-IDs
    integration.md      ← async/sync integration pattern
    job.md              ← scheduled/event-driven job
    report.md           ← generated report/document
```

Templates are generalized. The generation agent adapts each template to what
the project actually has — skipping sections that don't apply.

### 3.3 kenso:rules reference

Adapt the existing writing guide into a reference file that agents follow when
generating and optimizing documents. This is the quality standard — every generated
document must pass lint with a high score.

```
references/
  kenso:rules.md      ← adapted from writing_guide.md
```

### 3.4 The onboarding flow

Create the command, workflows, and agents for `/kenso:init`:

**Command:** `skills/kenso-init/SKILL.md` (~100 lines), with thin wrapper at `.claude/commands/kenso/init.md`

- Reads AGENTS.md / CLAUDE.md if present
- Runs `kenso ingest --json` for preliminary analysis
- Checks if `codebase/` and `domain/` folders exist in docs dir
  - If yes: asks reuse or regenerate
  - If no: proceeds to generation
- Presents area selection (codebase, domain, knowledge, decisions)
- Presents depth selection (essential, standard, exhaustive) with recommendation
- Shows proposed structure, asks confirmation
- Delegates to workflows sequentially

**Workflows:**

- `workflows/generate-codebase.md` — orchestrates codebase doc generation
- `workflows/generate-domain.md` — orchestrates domain doc generation
- `workflows/generate-knowledge.md` — orchestrates knowledge doc generation
- `workflows/optimize-files.md` — per-file frontmatter optimization
- `workflows/cross-analysis.md` — cross-file links, tags, categories

**Agents:**

- `agents/kenso:generator.md` — generates documentation from source code analysis.
  Receives a template + relevant source files, produces a complete .md file.
- `agents/kenso:optimizer.md` — optimizes frontmatter and headings of existing files.
  Receives a file + kenso:rules, produces an optimized version.
- `agents/kenso:analyst.md` — analyzes all files for cross-references. Receives
  file summaries (the map fichas), produces a plan.yml for `kenso apply`.

### 3.5 The map (fichas)

During optimization, each processed file gets a ficha in `.kenso/enhance/map/`:

```yaml
path: domain/orders/matching.md
title: Order Matching Engine
category: orders
tags: [matching, order-book, LOB, price-time-priority]
summary: "Describes how the matching engine processes orders using price-time priority"
concepts: [order matching, price-time priority, order book, limit order]
entities: [matching engine, CNMV, BME]
```

The fichas are the input for cross-analysis. They contain semantic information
(summary, concepts, entities) that only an LLM can extract — this is why the map
is produced by agents, not by kenso CLI.

The structural part of the ficha (path, title, tags, category) overlaps with what
`kenso ingest` already extracts from frontmatter. The semantic part (summary,
concepts, entities) is what the LLM adds.

### 3.6 Quality gate

After generation + optimization + cross-analysis + indexing, the command runs
`kenso lint --json` and checks the global score. If any generated file scores
below a threshold (e.g., 85), the agent fixes it before presenting the final
report.

The final report shows before/after metrics (before = the preliminary analysis
from step 0, after = post-optimization).

**Deliverable:** A user runs `/kenso:init`, answers a few questions, and gets a
complete knowledge base generated, optimized, indexed, and ready to query. The
full four-layer architecture is operational.

---

## Phase 4 — `/kenso:update`: keep docs in sync

**Goal:** After code changes (a completed task, merged PRs, pre-release), the
user runs `/kenso:update` and the documentation stays in sync.

### 4.1 Status command (moved from Phase 1)

```bash
kenso status
```

Compares files on disk against the last known state. Reports new, modified, and
deleted files. Uses git if available (`git diff --name-only` against a stored SHA),
falls back to content hash comparison. State is stored in `.kenso/state.json`.

### 4.2 Change detection

The command runs `kenso status` to detect what changed. It presents the changes
and proposes actions:

- **New code without docs:** propose generating new documentation
- **Modified code with existing docs:** propose updating affected documents
- **Modified docs (manual edits):** propose re-optimizing frontmatter
- **Deleted files:** clean up orphaned docs (with confirmation)

### 4.3 Update workflow

`workflows/update-docs.md` orchestrates:

1. For new documentation: delegates to generation workflows from Phase 3
2. For modified documentation: delegates to kenso:optimizer agent
3. For cross-link changes: delegates to kenso:analyst agent
4. Runs `kenso ingest` to re-index
5. Reports before/after metrics

### 4.4 State tracking

After successful update, writes the current git SHA to `.kenso/state.json`.
Next `/kenso:update` uses this as the baseline for change detection.

### 4.5 Scope control

For large projects, updating all 200 files when only 5 changed would be wasteful.
The command only processes files in the change set (new + modified). Cross-analysis
runs on the full map but only proposes changes for affected files and their
immediate neighbors in the document graph.

**Deliverable:** The documentation lifecycle is complete — generate once, update
incrementally. The user has a sustainable workflow.

---

## Phase 5 — Consultation commands

**Goal:** Specialized ways to consume the knowledge base beyond `/kenso:ask`.

### 5.1 `/kenso:define`

Searches the KB for all context relevant to a task definition. Produces a
structured task spec with: context summary, affected entities, affected files,
applicable rules, integration points, acceptance criteria.

Reuses the search infrastructure from `/kenso:ask` but with a different
synthesis prompt — exhaustive context gathering instead of concise answering.

### 5.2 `/kenso:brainstorm`

Open exploration mode. Searches broadly, connects disparate parts of the KB,
generates ideas informed by documented architecture and constraints. The synthesis
prompt encourages creative connections rather than direct answers.

### 5.3 `/kenso:explain`

Code-context mode. The user references a file or pastes a snippet. The command
searches the KB for business context (rules, decisions, domain concepts) that
explain *why* the code exists, not just what it does.

All three commands follow the same pattern as `/kenso:ask`: single-file command,
no workflow/agent layer needed, different synthesis prompt. They are lightweight
to implement once `/kenso:ask` exists.

**Deliverable:** The full consultation surface is available. Users have four
distinct ways to interact with their KB, each optimized for a different need.

---

## Phase 6 — CI/CD integration

**Goal:** Automated documentation updates as part of the development pipeline.

### 6.1 Headless update

```bash
kenso update --ci
```

Runs the same logic as `/kenso:update` but without interactive prompts. All
decisions are automatic (apply all proposed changes, no confirmations). Exits
with a non-zero code if something fails.

### 6.2 PR creation

A wrapper script (or built-in flag) that:

1. Creates a branch (`kenso/update-docs`)
2. Runs `kenso update --ci`
3. Commits changes
4. Creates a PR with the before/after report as body

### 6.3 GitHub Action / GitLab CI template

Provide ready-to-use CI configuration:

```yaml
# .github/workflows/kenso:update.yml
on:
  push:
    branches: [main]
    paths: ['src/**']

jobs:
  update-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install kenso[yaml]
      - run: kenso update --ci
      - run: |
          git checkout -b kenso/update-docs
          git add docs/
          git commit -m "docs: kenso auto-update"
          gh pr create --title "docs: kenso auto-update" \
            --body "$(cat .kenso/report.md)"
```

**Deliverable:** Teams can automate documentation maintenance. Docs are updated
on every merge to main without manual intervention.

---

## Phase 0 — Search quality improvements

**Goal:** Strengthen the search engine before building the command layer on top.
These are independent of the slash command work and can be done in parallel with
Phase 1, or before it. Each is a self-contained task.

Detailed implementation prompts for each task exist in `kenso:improvement-roadmap.md`.

### 0.1 Tokenization improvements

- Content-side compound term expansion (camelCase, snake_case in indexed content)
- Hyphen and dot compound splitting (pre-commit, CI/CD, com.example.Class)
- Stop word filtering in queries (how, do, I, the, etc.)

Impact: High. Affects every search query. Addresses audit gaps 3, 4, 5.

### 0.2 Ingestion improvements

- Preamble merge for short intros (< 50 chars → merge into first chunk, don't discard)
- Deleted file cleanup (remove stale DB entries for files no longer on disk)
- `.kensoignore` support (gitignore-style exclusion patterns)

Impact: Medium. Reduces noise, prevents ghost results.

### 0.3 Synonym expansion

Configurable `.kenso/synonyms.yml` for project-level query expansion.
"k8s" automatically expands to also search "kubernetes".

Impact: High. Directly addresses vocabulary mismatch — the #1 cause of search failures.

### 0.4 Unlinked mention detection

Scan indexed content for entity/concept names that appear in documents but aren't
connected via `relates_to`. Report as part of lint.

Impact: High. Makes the document graph denser, improves relation re-ranking.

### 0.5 Fuzzy matching fallback

Levenshtein-based query correction when FTS5 returns zero results.
"kuberntes" → "did you mean: kubernetes?"

Impact: Medium. Safety net for typos.

### 0.6 Smart snippets

Detect which column matched (title, tags, content) and generate the snippet
accordingly. Add `match_source` field to results.

Impact: Medium. Helps the LLM understand why a result matched.

### Execution order for Phase 0

| Order | Task | Effort |
|-------|------|--------|
| 1 | 0.1 Tokenization | Small |
| 2 | 0.2 Ingestion | Small |
| 3 | 0.3 Synonyms | Medium |
| 4 | 0.4 Unlinked mentions | Small |
| 5 | 0.5 Fuzzy matching | Medium |
| 6 | 0.6 Smart snippets | Medium |

---

## Future — Near term (not scheduled, likely next after Phase 6)

Ideas that are well-defined but not in the initial roadmap. They extend the
core product without changing the architecture.

### `/kenso:refine`

A panel of virtual experts refines a task definition. The user runs `/kenso:define`
first to get an initial spec, then `/kenso:refine` to have it reviewed by
specialized perspectives: infrastructure, security, UX/UI, operations, QA, copy.

Each expert consults the KB for their domain and adds concerns, edge cases,
or requirements the initial definition missed. Output is an enriched task spec
with sections per expert.

Depends on: Phase 5 (`/kenso:define`).

### Deprecated content support

A `deprecated: true` frontmatter field (or `status: deprecated` with optional
`superseded_by: path/to/new-doc.md`). Deprecated documents remain indexed and
searchable — the agent can find them to understand historical context, old
workflows, legacy code. But search results flag them clearly, and the agent
knows to prefer the superseding document when both match.

Lint warns if a deprecated doc has no `superseded_by` link.

### TODOs / pending work awareness

A `kenso todos` command or frontmatter convention (`todos:` field or `## TODOs`
section) that surfaces pending work, known gaps, and planned improvements across
the KB. The agent can factor these into task definitions — "this area has a known
gap, see TODO in docs/domain/settlement.md".

### Eval tool improvements

Extend the existing eval harness into a user-facing quality measurement tool:

- `kenso eval` — run a suite of query→expected-document pairs, report pass/fail
- `kenso eval --compare baseline` — compare against a saved snapshot
- `kenso eval --generate` — auto-generate test cases from `predicted_queries` and
  `answers` fields in frontmatter
- Track metrics over time: MRR, nDCG@k, Recall@k
- Detect regressions when search config or documents change

This is the tool that proves whether a batch of improvements has real impact.
Measurable, reproducible, deterministic.

### Changelog / git history access

Allow the agent to query git history through the KB: when was something
implemented, who changed it, what was the commit message. Could be a
`/kenso:history` command or an extension of `/kenso:explain` that adds
git blame context.

Implementation options: index git log entries as a special document category,
or query git directly at search time.

### Additional runtimes

Gemini CLI, OpenCode, Windsurf native command support in `kenso install`.
Same canonical format, different converters.

### BM25 score simulation during authoring

A lint mode that simulates BM25 scores for likely queries against a document
draft. `kenso lint --simulate` reads `predicted_queries` from frontmatter, runs
each against the index, and reports where the document ranks.

"Your doc ranks #7 for 'rate limit config' — adding 'rate-limit' to tags would
improve it."

Analogous to SEO preview tools. Requires the index to exist (unlike regular lint
which works on files only).

### Deterministic keyword extraction

`kenso suggest-tags ./docs/` runs TF-IDF or YAKE across the corpus, identifies
distinctive terms per document, and proposes tag candidates. Purely deterministic,
no LLM cost. Could feed into the optimization workflow as candidates that the
LLM refines.

Would need a lightweight Python NLP library (YAKE is pip-installable).

### Vocabulary drift detection

After each `kenso ingest`, compare the current term frequency distribution
against a stored baseline. Flag new high-frequency terms that appear in 5+
documents but aren't in any document's tags. These are emerging vocabulary
that the team uses but hasn't formalized.

Low-moderate effort — TF-IDF computation is already implicit in BM25.

### Search log analysis

`kenso serve` logs all queries and result counts to a file. `kenso analyze-logs`
reads the log, groups zero-result queries by similarity, and suggests which
documents should be enriched to cover them.

Enterprise search best practice. Low effort for logging, moderate for analysis.

---

## Future — Long term (research/design needed)

Ideas that require significant design work or represent a different product scope.

### Multiple databases

`kenso search` queries multiple databases simultaneously. For large organizations
where each team maintains their own KB but cross-team queries are needed.

Design questions: how to merge results across DBs (RRF?), how to handle
conflicting categories/tags, how to scope queries ("search only in my team's KB"
vs "search everywhere").

### Real-time API data sources

A JSON configuration that defines API endpoints returning structured data (products,
users, inventory, etc.) that the agent can consult alongside the static KB.

Design questions: caching strategy, freshness guarantees, schema mapping to make
API data searchable alongside documents, authentication.

### Web indexing

Index web pages as part of the KB. Could be useful for including external
documentation (vendor docs, regulatory references, API specs).

Design questions: whether to build this or integrate with existing tools
(Jina, Firecrawl, etc.), storage of web content vs just metadata, refresh
frequency, copyright considerations.

### Jira / issue tracker integration

Index Jira tickets as a searchable layer. The agent can see what's in the
backlog, what's in the current sprint, what's completed. `/kenso:define`
could create Jira tickets directly.

Design questions: MCP vs direct API, real-time vs periodic sync, how to
handle ticket updates, authentication per user vs service account.

### Multi-repo support

A single kenso KB spanning multiple repositories. The agent can query across
repos and understand cross-repo dependencies.

Design questions: where the DB lives, how ingest works across repos, how
`kenso install` works when commands need to reference multiple doc roots.

### API versioning

Multiple versions of the KB coexisting (v1, v2). For teams with parallel
development streams that need to query documentation specific to their version.

Design questions: versioned databases vs versioned queries, branch-based
versioning (git branches = KB versions), merge strategy.

### Controlled vocabulary as formal taxonomy

Evolve `.kenso/synonyms.yml` into a SKOS-inspired `.kenso/vocabulary.yml` with
prefLabel, altLabel, broader/narrower relationships, and definitions:

```yaml
concepts:
  - id: api-design
    prefLabel: API Design
    altLabels: [REST API, API architecture, endpoint design]
    broader: architecture
    related: [authentication, versioning]
    definition: Patterns and practices for designing programmatic interfaces
```

The optimization workflow and lint would validate against this vocabulary. New
terms would be proposed for addition automatically.

Design questions: migration path from simple synonyms.yml, whether the
complexity is justified for small teams, governance process for vocabulary
changes. Based on ANSI/NISO Z39.19, ISO 25964, W3C SKOS standards.

---

## Phase dependencies

```
Phase 0 ─── Search quality improvements (independent, can run anytime)

Phase 1 ─── CLI foundations
   │
   ├──→ Phase 2 ─── /kenso:ask (proof of concept)
   │       │
   │       ├──→ Phase 5 ─── consultation commands (/define, /brainstorm, /explain)
   │       │       │
   │       │       └──→ /kenso:refine (future, depends on /define)
   │       │
   │       └──→ Phase 3 ─── /kenso:init (generate + optimize)
   │               │
   │               └──→ Phase 4 ─── /kenso:update
   │                       │
   │                       └──→ Phase 6 ─── CI/CD
```

Phase 0 has no dependencies on any other phase — it improves the existing
search engine independently. Phases 2 and 3 can run in parallel after Phase 1.
Phase 5 only depends on Phase 2 (the install system + command format).
Phase 3 is the critical path for the full lifecycle.
