<p align="center">
  <img src="https://github.com/fvena/kenso/raw/main/assets/kenso_logo.svg" alt="kenso" height="140" />
</p>

<h3 align="center" style="margin-bottom: 0.3em;">
  Talk to your docs
</h3>

<p align="center" style="max-width: 720px; margin: 0.5em auto 1.5em auto; color: #6b7280;">
  kenso turns a folder of Markdown docs into a knowledge base you can talk to from your LLM. Ask questions, define tasks, brainstorm ideas — from your own docs. Zero config. No infrastructure. Always deterministic.
</p>

<p align="center">
  <a href="https://pypi.org/project/kenso/"><img alt="PyPI" src="https://img.shields.io/pypi/v/kenso?color=blue"></a>
  <a href="https://pypi.org/project/kenso/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/kenso"></a>
  <a href="https://github.com/fvena/kenso/actions"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/fvena/kenso/ci.yml"></a>
  <a href="https://codecov.io/gh/fvena/kenso"><img alt="Coverage" src="https://img.shields.io/codecov/c/github/fvena/kenso"></a>
  <!-- <a href="https://pypi.org/project/kenso/"><img alt="Downloads" src="https://img.shields.io/pypi/dm/kenso"></a> -->
  <a href="https://github.com/fvena/kenso/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/fvena/kenso"></a>
</p>

<p align="center">
  <a href="https://fvena.github.io/kenso/">Docs</a> ·
  <a href="https://fvena.github.io/kenso/guide/getting-started">Getting Started</a> ·
  <a href="https://fvena.github.io/kenso/guide/writing-docs">Writing Guide</a>
</p>

## Why kenso

Your documentation already has the answers. But finding them means remembering which file, scanning entire documents, or piecing together information scattered across multiple places. kenso lets you ask one question and get the right answer.

- **Direct answers** — finds the right paragraph without reading the whole doc.
- **Cross-document reasoning** — one question, ten docs, one synthesized answer.
- **Natural queries** — search how you think, not how the author wrote.
- **Cross-domain** — bridge code and business rules in one question.
- **Define tasks, brainstorm, refine, explain** — think with your docs, not from guesses.
- **Generate docs from code** — create documentation from your codebase.

## Installation

### With uv (recommended)

```bash
uv tool install kenso          # → .agents/skills/ (standard — Codex, Cursor, Gemini CLI, ...)
uv tool install kenso --claude # → .claude/commands/ + .claude/skills/
uv tool install kenso --codex  # → .codex/skills/ (legacy Codex projects)
```

### With pip

```bash
pip install kenso[yaml]       # install with YAML frontmatter support

kenso install                 # → .agents/skills/ (standard — Codex, Cursor, Gemini CLI, ...)
kenso install --claude        # → .claude/commands/ + .claude/skills/
kenso install --codex         # → .codex/skills/ (legacy Codex projects)
```

### Claude Code

Add permissions so kenso CLI runs without confirmation prompts:

```json
// .claude/settings.json
{
  "permissions": {
    "allow": [
      "Bash(kenso search:*)",
      "Bash(kenso stats:*)",
      "Bash(kenso lint:*)",
      "Bash(kenso ingest:*)"
    ]
  }
}
```

## Quick Start

Now open your LLM and initialize kenso:

```bash
# Claude Code
/kenso:init docs/           # initialize kenso with your docs
/kenso:ask How is code deployed to production?

# Codex CLI
$kenso:init docs/           # initialize kenso with your docs
$kenso:ask How is code deployed to production?
```

> kenso works with any Markdown file. <br />
> To improve retrieval quality, see [Writing Effective Documents](#writing-effective-documents).

## Commands

### Lifecycle

| Command | What it does |
|---------|--------------|
| `kenso:init` | Analyzes your project, generates documentation, optimizes for retrieval, and indexes. Takes you from zero to a queryable knowledge base. |
| `kenso:update` | Detects code and doc changes, updates affected documentation, re-optimizes cross-links, re-indexes. Shows before/after metrics. |
| `kenso update --ci` | Headless version for CI/CD pipelines. Updates docs and opens a PR with a quality report. |

### Consultation

| Command | What it does |
|---------|--------------|
| `kenso:ask` | Ask a question, get a sourced answer from your docs. |
| `kenso:define` | Define a task with full project context — affected entities, rules, files, integration points, and acceptance criteria. |
| `kenso:brainstorm` | Explore ideas and trade-offs grounded in your real architecture and constraints. |
| `kenso:explain` | Understand why code exists — business rules, design decisions, domain context behind the implementation. |

## How it compares

|  | Plain LLM | Embedding RAG | kenso |
|---|:---:|:---:|:---:|
| **Infrastructure** | — | Model + vector DB + pipeline | `pip install` |
| **Knows your project** | ✗ | Partial | ✓ |
| **Generates docs from code** | ✗ | ✗ | ✓ |
| **Keeps docs in sync** | ✗ | ✗ | ✓ |
| **Source citations** | ✗ | Partial | ✓ |
| **Deterministic** | — | ✗ | ✓ |
| **Semantic understanding** | ✓ | ✓ | Relies on LLM |
| **Vocabulary-independent** | ✓ | ✓ | ✗ |
| **Works with any content** | ✓ | ✓ | Markdown only |
| **Inspectable ranking** | — | ✗ | ✓ |
| **CI/CD automation** | — | ✗ | ✓ |
| **Free** | ✗ | ✗ | ✓ |

kenso uses BM25 keyword search over SQLite — no embeddings, no vector database, no API costs for search. The LLM already understands meaning; kenso gives it the right source text

## Writing Effective Documents

kenso works with any Markdown. Adding frontmatter improves retrieval:

```yaml
---
title: CI/CD Deployment Pipeline
category: infrastructure
tags: deployment, CI/CD, rollback, blue-green
aliases:
  - deploy pipeline
  - continuous deployment
answers:
  - How is code deployed to production?
relates_to:
  - path: infrastructure/monitoring.md
    relation: receives_from
---
```

Specific titles are indexed at 10× weight. Tags with synonyms your team uses help with vocabulary mismatch. A summary paragraph before the first H2 ensures the overview is always searchable.

See the full [Writing Guide](https://fvena.github.io/kenso/guide/writing-docs) for field reference, structure tips, relation types, and a pre-commit checklist.

## Performance

100% hit rate and 97.2% MRR across a 36-query eval harness covering 10 retrieval categories. Zero regressions across development. Run it yourself with `python tests/eval/eval_harness.py`.

## Roadmap

kenso is under active development. Current focus areas:

- [ ] **Search quality** — Tokenization for compound terms (camelCase, snake_case), synonym expansion via `.kenso/synonyms.yml`, fuzzy matching for typos, smart snippets showing why a result matched.

- [ ] **Near term** — `/kenso:refine` (expert panel review of task definitions), deprecated document support, BM25 score simulation during authoring, search log analysis.

- [ ] **Long term** — Multi-repo knowledge bases, real-time API data sources, Jira integration, controlled vocabulary as formal taxonomy.

See the full [roadmap](docs/roadmap.md) for details.

## Troubleshooting

**kenso search returns no results** — Run `kenso stats` to check if docs are indexed. If zero docs, run `kenso ingest <path>`.

**"No such table: chunks"** — The database schema changed. Delete the database file (`.kenso/docs.db` or `~/.local/share/kenso/docs.db`) and re-ingest.

**MCP server not connecting** — Verify the command path is correct. If installed in a venv, use the full path (e.g. `/path/to/.venv/bin/kenso`). Restart your editor after changing MCP config.

## License

MIT

---

**kenso** — inspired by Japanese 検索 (kensaku): to search.
