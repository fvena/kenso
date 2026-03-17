# Kenso — Vision

## What kenso is

kenso lets you talk to your documentation through your LLM. Instead of remembering which
file has the answer, scanning entire documents, or piecing together scattered information,
you ask a question and get the right answer from your own docs.

Under the hood, kenso turns a folder of Markdown files into a searchable knowledge base —
indexing with BM25, providing keyword search with weighted columns, and exposing results via
MCP or CLI. Zero infrastructure, fully deterministic, works with any Markdown.

This already exists and works well.

## What kenso is becoming

kenso is expanding from a **search tool** to a **complete knowledge base lifecycle system**.
Four functions, one product:

1. **Generate** — Create documentation from a codebase (structure, domain, entities, workflows)
2. **Optimize** — Improve existing documentation for retrieval quality (frontmatter, headings, cross-links)
3. **Consult** — Search and reason over the knowledge base (what already exists today)
4. **Update** — Keep documentation in sync with code changes

The search engine is the foundation. The new capabilities are layers on top that ensure the
knowledge base has high-quality content for the search engine to work with.

---

## Architecture: three layers

```
┌─────────────────────────────────────────────────┐
│  Skills (.agents/skills/)                       │  ← what the user sees
│  /kenso:ask (Claude Code)  $kenso-ask (Codex)   │
│  Autodiscovery in Cursor / Copilot / Gemini     │
│  SKILL.md files — universal format              │
├─────────────────────────────────────────────────┤
│  Kenso CLI                                      │  ← infrastructure
│  kenso ingest  kenso search  kenso lint  ...    │
│  Python binary, deterministic, no LLM           │
├─────────────────────────────────────────────────┤
│  MCP Server                                     │  ← optional adapter
│  kenso serve                                    │
│  For editors and external integrations          │
└─────────────────────────────────────────────────┘
```

**Skills** are the primary interface. They use the Agent Skills standard (SKILL.md with YAML
frontmatter) — a universal format adopted by Codex, Cursor, Copilot, and Gemini CLI. In Claude
Code, thin slash commands in `.claude/commands/kenso/` delegate to the skills. The user works
inside their LLM agent and never leaves the session. Skills orchestrate the full lifecycle —
generating docs, optimizing them, querying the KB, updating after changes. They invoke kenso CLI
internally via bash.

**Kenso CLI** is the deterministic layer. It handles indexing, search, linting, and any
operation that doesn't require an LLM. It is fast, predictable, and the single source of
truth for the index. The user rarely invokes it directly — the commands do.

**MCP server** is an optional adapter for editors (Cursor, VS Code, Claude Desktop) and
external integrations. It wraps kenso CLI's search capabilities in the MCP protocol.
It remains the primary interface for users who don't work in Claude Code or Codex.

---

## User surface

### Lifecycle commands (inside the LLM)

| Command | When | What it does |
|---------|------|--------------|
| `/kenso:init` | First time using kenso | Interactive onboarding: analyzes project, asks what to document, generates + optimizes + indexes. If kenso:generated docs already exist, asks whether to reuse or regenerate. |
| `/kenso:update` | After code or doc changes | Detects changes (git-based), updates affected docs, re-optimizes increments, re-indexes. Shows before/after metrics. |

### Consultation commands (inside the LLM)

| Command | When | What it does |
|---------|------|--------------|
| `/kenso:ask` | Direct question | Searches KB, synthesizes concise answer with source citations. |
| `/kenso:define` | Define a task or ticket | Searches KB for context, generates task spec with affected entities, files, rules, and acceptance criteria. |
| `/kenso:brainstorm` | Open exploration | Searches KB, generates ideas and trade-offs informed by documented architecture and constraints. |
| `/kenso:explain` | Understand code | Searches KB for business context behind code. Connects implementation to rules, decisions, and domain concepts. |

### CLI (terminal, scripts, CI/CD)

| Command | When | What it does |
|---------|------|--------------|
| `kenso search` | Quick terminal lookup | Direct keyword search against the index. |
| `kenso ingest` | Reindex after changes | Scan, hash, chunk, index. Also runs lint and reports quality metrics. |
| `kenso lint` | Check doc quality | Score documents against retrieval quality rules. |
| `kenso stats` | Inspect the index | Document count, chunk count, storage size, category breakdown. |
| `kenso serve` | Start MCP server | For editor integrations and remote access. |
| `kenso install` | Setup skills | Install skills to `.agents/skills/` (universal standard). `--claude` adds slash commands for Claude Code. `--codex` installs to `.codex/skills/` (legacy). |

### CI/CD

| Command | When | What it does |
|---------|------|--------------|
| `kenso update --ci` | Post-merge, pre-release | Headless version of `/kenso:update`. Applies changes, creates PR. |

---

## How commands work: the layered execution model

Following the thin-orchestrator pattern from GSD, each command delegates through four layers:

```
Command (~80 lines)        Entry point. Loads minimal context, presents choices,
    │                      delegates to the right workflow.
    ▼
Workflow (~300 lines)      Orchestration logic. Coordinates agents, manages
    │                      state transitions, calls kenso CLI for deterministic ops.
    ▼
Agent (~1000 lines)        Domain specialist. Has full expertise for one job
    │                      (generate docs, optimize frontmatter, analyze cross-links).
    │                      Runs in fresh context window when possible.
    ▼
Kenso CLI                  Deterministic operations. No LLM. Fast.
                           kenso ingest, kenso lint, kenso search, kenso apply.
```

Example: `/kenso:init` invocation chain:

```
/kenso:init (command)
  → reads AGENTS.md / CLAUDE.md for project context
  → runs `kenso ingest --json` for preliminary analysis
  → asks user: which areas? which depth?
  → shows proposed structure, asks confirmation
  → delegates to generate-codebase workflow
      → spawns kenso:generator agent with template + source files
      → agent produces .md files following kenso:rules
      → workflow saves files, moves to next area
  → delegates to optimize-files workflow
      → spawns kenso:optimizer agent per file
      → agent enriches frontmatter, improves headings
  → delegates to cross-analysis workflow
      → spawns kenso:analyst agent with all file summaries
      → agent produces cross-link plan
      → workflow applies plan via `kenso apply`
  → runs `kenso ingest` for final indexing
  → runs `kenso lint --json` for final metrics
  → presents before/after report
```

Each layer has access to:

- **References** — documentation loaded on demand (kenso:rules, quality metrics guide, etc.)
- **Templates** — document templates for generated content (entity, action, workflow, etc.)

References and templates are not loaded until the agent needs them. This keeps context clean.

---

## What kenso generates

When `/kenso:init` generates documentation, it creates files in folders it owns. Files
outside these folders are the user's — kenso indexes and optimizes their metadata but
never rewrites their content.

### Folder ownership

```
docs/                              ← root (configurable)
  codebase/                        ← kenso:owned: generated from source code
  domain/                          ← kenso:owned: generated from domain analysis
  knowledge/                       ← kenso:owned: deep docs (entities, rules, actions...)
  decisions/                       ← kenso:owned: ADRs
  *.md (loose files)               ← user-owned: kenso indexes + optimizes metadata only
  guides/                          ← user-owned: kenso indexes + optimizes metadata only
  ...
```

Kenso identifies its own files by folder convention. If `codebase/` and `domain/` exist
with content, `/kenso:init` asks whether to reuse or regenerate — covering the case where
documentation has gone stale and the user wants to start fresh.

### Depth levels

The user chooses how much documentation to generate during `/kenso:init`:

| Level | What it produces | Typical size | Time |
|-------|-----------------|-------------|------|
| Essential | 1 file per area. High-level overview. | ~5 files | ~2 min |
| Standard | 1 file per module/concept. Covers 80% of queries. | ~25 files | ~8 min |
| Exhaustive | 1 file per entity, action, workflow, job, report. | ~80+ files | ~25 min |

Kenso recommends a level based on preliminary project analysis (language, framework count,
entity count, integration count). The user can override.

### Document templates

Each generated document follows a template from `templates/`. Templates are generalized —
not all fields apply to every project. The generation agent adapts the template to what the
project actually has. A simple REST API won't get `integration-checkpoints` sections. A
regulated platform with async message queues will.

Key template categories:

- **Codebase** — architecture, structure, stack, conventions, testing, integrations, concerns
- **Domain** — project identity, actors, domain model, workflows
- **Knowledge** — entities (with lifecycle/state machines), rules (with BR-IDs), actions
  (with preconditions/effects), workflows (with flow diagrams), integrations, jobs, reports
- **Decisions** — ADR index + individual ADR files

---

## Multi-runtime support

Skills are authored once in the **Agent Skills standard** (SKILL.md with YAML frontmatter)
and installed without format conversion. Each runtime discovers them natively.

### Default install (`kenso install`)

```
.agents/
  skills/
    kenso-ask/
      SKILL.md                    ← universal skill file
    kenso-init/
      SKILL.md
    ...
```

The `.agents/skills/` directory is the universal standard. Cursor, Copilot, and
Gemini CLI discover skills here automatically.

### Claude Code (`kenso install --claude`)

```
.claude/
  skills/
    kenso-ask/
      SKILL.md                    ← same universal skill file
    kenso-init/
      SKILL.md
    ...
  commands/
    kenso/
      ask.md                      ← thin wrapper (~5 lines)
      init.md                     ← references @.claude/skills/kenso-init/SKILL.md
      update.md
      ...
  kenso/                          ← support files
    workflows/
    agents/
    references/
    templates/
  settings.json                   ← tool permissions
```

Slash commands in `.claude/commands/kenso/` are thin wrappers (~5 lines) that
reference the skill via `@.claude/skills/kenso-ask/SKILL.md`. The user invokes
`/kenso:ask` in Claude Code, which loads the skill.

### Codex CLI (`kenso install --codex`)

```
.codex/
  skills/
    kenso-ask/
      SKILL.md                    ← same universal skill file
    kenso-init/
      SKILL.md
    ...
```

Legacy path. Same SKILL.md files, installed to `.codex/skills/` instead.

### What each flag creates

| Flag | Skills | Slash commands | Settings |
|------|--------|---------------|----------|
| (none) | `.agents/skills/kenso-*/SKILL.md` | — | — |
| `--claude` | `.claude/skills/kenso-*/SKILL.md` | `.claude/commands/kenso/*.md` | `.claude/settings.json` |
| `--codex` | `.codex/skills/kenso-*/SKILL.md` | — | — |

No format conversion is needed between runtimes — SKILL.md is the universal format.
Workflows, agents, references, and templates live in `.claude/kenso/` (Claude Code)
and are loaded via `@` path references from the skills.

---

## What already exists (implemented)

| Component | Status |
|-----------|--------|
| `kenso ingest` | ✓ Full pipeline: scan, hash, parse frontmatter, chunk by H2, build searchable_content, FTS5 index, extract relates_to |
| `kenso search` | ✓ FTS5 cascade (AND → NEAR → OR), 3× candidates, dedup, relation re-ranking, metadata enrichment |
| `kenso lint` | ✓ 18 rules, score calculation, summary + detail + JSON modes |
| `kenso stats` | ✓ Document count, chunk count, storage, category breakdown |
| `kenso serve` | ✓ MCP server (stdio + streamable-http), 4 tools (search_docs, search_multi, get_doc, get_related) |
| Writing guide | ✓ Complete guide for document authors |
| Eval harness | ✓ 36-query harness, 10 retrieval categories, regression tracking |

## What needs to be built

| Component | Priority | Dependencies |
|-----------|----------|-------------|
| CLI changes (ingest --json, lint in ingest, status, apply) | Phase 1 | None |
| Install system (skills + Claude Code slash command wrappers) | Phase 1 | None |
| `/kenso:ask` command (simplest command, proof of concept) | Phase 2 | Phase 1 |
| `/kenso:init` command (generate + optimize + index) | Phase 3 | Phase 2, templates |
| Document templates (codebase, domain, knowledge) | Phase 3 | None (content work) |
| `/kenso:update` command | Phase 4 | Phase 3 |
| `/kenso:define`, `/kenso:brainstorm`, `/kenso:explain` | Phase 5 | Phase 2 |
| CI/CD integration (`kenso update --ci`) | Phase 6 | Phase 4 |

---

## Key design decisions

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| Language | Python only | kenso CLI is Python. Commands are Markdown. No second runtime needed. |
| Canonical format | Agent Skills standard (SKILL.md) | Universal format adopted by Codex, Cursor, Copilot, Gemini CLI. Claude Code gets thin slash command wrappers on top. |
| Command naming | kenso:X for Claude Code slash commands, kenso-X for skill names | Colon uses Claude Code's subdirectory convention (.claude/commands/kenso/X.md). Hyphen is the universal skill name. |
| Command architecture | GSD pattern: command → workflow → agent → tool | Proven pattern for context efficiency. Thin orchestrators, fresh agent contexts. |
| Lint inside ingest | `kenso ingest` always runs lint and reports quality | One command for the user, not two. Lint becomes invisible infrastructure. |
| Incremental detection | Git-based (`git diff --name-only` against stored SHA) | Simple, reliable, already available in any project. |
| Generated file ownership | By folder convention (`codebase/`, `domain/`, `knowledge/`) | No metadata markers needed. User files outside these folders are never rewritten. |
| MCP role | Optional adapter, not primary interface | Users in Claude Code / Codex get better UX through slash commands. MCP for editors. |
| Map (cross-analysis fichas) | Generated by LLM during optimize, not by kenso CLI | Contains semantic info (summary, concepts) that requires LLM. CLI can't produce it. |
| Depth levels | User chooses (essential/standard/exhaustive), kenso recommends | Transparent cost/time trade-off. No hidden token consumption. |
| Unlinked detection | Part of lint, not a separate command | From the user's perspective it's just another quality metric. |
