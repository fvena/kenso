# Kenso — Slash Command Specs

Reference: [VISION.md](./VISION.md) · [ROADMAP.md](./ROADMAP.md)

This document defines every slash command kenso installs. Each spec is the
reference for implementing the canonical command file and its supporting
workflows, agents, and references.

---

## Architecture recap

Every command follows the same execution model:

```
Skill (SKILL.md)  →  Workflow  →  Agent  →  Kenso CLI
       ↑
Slash command (Claude Code only, thin wrapper)
```

Not every skill needs all layers. Simple skills (ask, define, brainstorm,
explain) are self-contained — no workflow or agent layer. Complex skills
(init, update) delegate through the full stack.

The skill (SKILL.md) is the universal entry point. In Claude Code, a thin
slash command wrapper delegates to the skill. In other runtimes (Codex,
Cursor, Copilot, Gemini CLI), the skill is discovered automatically.
Everything below it — workflows, agents, CLI — is invoked by the skill,
never by the user directly.

---

## Command index

| Command | Phase | Category | Layers used |
|---------|-------|----------|-------------|
| `/kenso:init` | 3 | Lifecycle | Command → Workflow → Agent → CLI |
| `/kenso:update` | 4 | Lifecycle | Command → Workflow → Agent → CLI |
| `/kenso:ask` | 2 | Consultation | Command → CLI |
| `/kenso:define` | 5 | Consultation | Command → CLI |
| `/kenso:brainstorm` | 5 | Consultation | Command → CLI |
| `/kenso:explain` | 5 | Consultation | Command → CLI |
| `/kenso:refine` | Future | Consultation | Command → Agents → CLI |

---

## `/kenso:init`

### Purpose

First-time setup. Takes a project from zero (or from unoptimized docs) to a
complete, indexed, high-quality knowledge base. Interactive onboarding that
adapts to what the project already has.

### Preconditions

- kenso is installed (`pip install kenso[yaml]`)
- Commands are installed (`kenso install --claude` or `--codex`)
- A project exists with source code

### User experience

The user types `/kenso:init` and the command drives the conversation. The user
answers a few questions, confirms a proposal, and waits while kenso generates,
optimizes, and indexes. At the end, they see a quality report and can immediately
start querying.

### Flow

```
Step 0 — Preliminary analysis (silent, no interaction)
Step 1 — Area selection (interactive)
Step 2 — Depth selection (interactive)
Step 3 — Structure proposal (interactive, confirmation)
Step 4 — Generation (automated, shows progress)
Step 5 — Optimization (automated, shows progress)
Step 6 — Cross-analysis (automated)
Step 7 — Indexation + final report (automated)
```

### Step 0 — Preliminary analysis

The command gathers context silently before presenting anything to the user.

**Inputs read:**
- `AGENTS.md` or `CLAUDE.md` at repo root (if they exist) — project context
- Project files: `package.json`, `pom.xml`, `Cargo.toml`, `pyproject.toml`,
  `go.mod`, etc. — to detect language, framework, dependencies
- Source directory structure (1-2 levels deep)
- Existing docs directory (if configured or if `./docs` exists)

**CLI invoked:**
```bash
kenso ingest ./docs --json    # if docs exist — preliminary analysis
```

**What it determines:**
- Languages and frameworks in use
- Approximate entity/model count (by scanning for model/entity files)
- Integration count (by scanning for SDK imports, queue configs, API clients)
- Test infrastructure present
- Existing documentation: how many files, what quality score
- Whether `codebase/`, `domain/`, `knowledge/` folders exist (kenso:generated)

**Output:** Internal analysis object, not shown to user yet.

### Step 1 — Area selection

The command presents results of the analysis and asks what to document.

```
Project analyzed: my-project
  Java 17 / Spring Boot 3.2 / Maven
  127 entities · 43 controllers · 18 async services
  3 integrations (SQS, S3, SMTP)
  Existing docs: 3 files in ./docs (not kenso:generated)

What areas do you want to document?

  ☑ Codebase     Architecture, structure, conventions, stack
  ☑ Domain       Entities, actors, rules, workflows
  ☐ Knowledge    Deep docs: each entity, action, integration in its own file
  ☐ Decisions    Architecture Decision Records (ADRs)

  ★ Recommended: Codebase + Domain + Knowledge
    (127 entities and async integrations suggest complex domain)
```

If kenso:generated folders already exist:

```
kenso:generated documentation found:
  codebase/   14 files (generated 2026-03-10)
  domain/      8 files (generated 2026-03-10)

  1. Use existing documentation — re-optimize and re-index only
  2. Regenerate from scratch — useful if code has changed significantly
```

### Step 2 — Depth selection

```
Depth level:

  ○ Essential      ~5 files · ~2 min · low token cost
    One overview file per area.

  ○ Standard       ~25 files · ~8 min · moderate token cost
    One file per module or main concept. Covers 80% of queries.

  ● Exhaustive     ~80 files · ~25 min · high token cost
    One file per entity, action, workflow, job, report.
    Maximum search precision.

  ★ Recommended: Exhaustive
    (regulated platform with async integrations — queries will be
     about specific states, rules, and bypasses)

  ⚠ Higher depth = more generation time and token consumption.
    You can start with Standard and expand later with /kenso:update.
```

### Step 3 — Structure proposal

Based on selections, the command shows the full file tree it will create:

```
Proposed structure:

📂 docs/
  📂 codebase/
    📄 architecture.md
    📄 structure.md
    📄 stack.md
    ...
  📂 domain/
    📄 project.md
    📄 actors.md
    📄 domain-model.md
    ...
  📂 knowledge/
    📂 entities/         ~18 files
    📂 rules/            ~6 files
    📂 actions/          ~22 files
    ...

  Existing files (will be indexed and optimized, not rewritten):
    📄 docs/PROJECT.md
    📄 docs/API-GUIDE.md

Total: ~84 files · ~25 min estimated

Proceed? (you can exclude categories, e.g. "skip reports and jobs")
```

### Step 4 — Generation

Delegates to generation workflows. Each workflow spawns the kenso:generator
agent with the appropriate template and source files.

**Workflows invoked (sequentially):**
- `workflows/generate-codebase.md` — if codebase selected
- `workflows/generate-domain.md` — if domain selected
- `workflows/generate-knowledge.md` — if knowledge selected (iterates
  over entities, actions, workflows, etc.)

**Progress shown:**
```
Generating documentation...

Codebase [7/7] ████████████████████ ✓
Domain   [3/3] ████████████████████ ✓
Knowledge — entities [8/18] █████████░░░░░░░░░░░
  order.md         ✓  (12 fields, 8 states, 4 rules)
  issuance.md      ✓  (15 fields, 6 states, 7 rules)
  ...
```

Each generated file follows the template from `templates/` and the rules
from `references/kenso:rules.md`. Files are written to disk as they're
generated.

### Step 5 — Optimization

Optimizes all files — both generated and user-owned. For generated files,
this mainly catches anything the generator missed (edge cases in frontmatter,
heading specificity). For user files, this adds/improves frontmatter without
touching content.

**Workflow invoked:** `workflows/optimize-files.md`

Spawns kenso:optimizer agent per file (or in batches if many files). Each
file gets:
- Frontmatter enrichment (tags, aliases, predicted_queries, answers)
- Heading improvement (generic → specific)
- Ficha generation (saved to `.kenso/enhance/map/`)

**CLI invoked per file:**
```bash
kenso lint --file <path> --json    # validate inline
```

### Step 6 — Cross-analysis

Analyzes all fichas to find relationships between documents.

**Workflow invoked:** `workflows/cross-analysis.md`

Spawns kenso:analyst agent with all fichas. The agent produces a plan:
- Which files should link to each other (relates_to)
- Tags to propagate across related files
- Categories to normalize

**CLI invoked:**
```bash
kenso apply .kenso/enhance/plan.yml    # apply cross-links deterministically
```

### Step 7 — Indexation + final report

**CLI invoked:**
```bash
kenso ingest ./docs --json    # full re-index with lint
```

**Quality gate:** If any generated file scores below 85, the command
auto-fixes it before presenting the report.

**Final output:**
```
📊 Knowledge Base ready
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                     Before    After
Score:                 42        96

Files:                 87
  Generated:           84
  User (optimized):     3

Cross-links:           67
Tags:                 142 unique
Rules documented:      48

Try: /kenso:ask How does the matching engine work?
```

**State saved:**
```bash
# .kenso/state.json
{
  "last_optimize_sha": "<current git SHA>",
  "last_optimize_timestamp": "2026-03-16T..."
}
```

### Files involved

| Type | Files |
|------|-------|
| Skill | `skills/kenso-init/SKILL.md` |
| Slash command | `.claude/commands/kenso/init.md` (thin wrapper, Claude Code only) |
| Workflows | `workflows/generate-codebase.md`, `workflows/generate-domain.md`, `workflows/generate-knowledge.md`, `workflows/optimize-files.md`, `workflows/cross-analysis.md` |
| Agents | `agents/kenso:generator.md`, `agents/kenso:optimizer.md`, `agents/kenso:analyst.md` |
| References | `references/kenso:rules.md`, `references/onboarding-flow.md` |
| Templates | `templates/codebase/*`, `templates/domain/*`, `templates/knowledge/*` |
| CLI | `kenso ingest --json`, `kenso lint --file --json`, `kenso apply` |

---

## `/kenso:update`

### Purpose

Keep documentation in sync after code or doc changes. Detects what changed,
proposes updates, and applies them. Incremental — only processes affected files.

### Preconditions

- `/kenso:init` has been run at least once (`.kenso/state.json` exists)
- kenso index exists

### User experience

The user types `/kenso:update` after finishing a task, merging PRs, or before
a release. The command shows what changed and what it proposes to do. The user
confirms and the command applies changes.

### Flow

```
Step 0 — Detect changes (deterministic)
Step 1 — Present changes and propose actions (interactive)
Step 2 — Apply updates (automated)
Step 3 — Re-optimize + cross-analysis (automated)
Step 4 — Re-index + report (automated)
```

### Step 0 — Detect changes

**CLI invoked:**
```bash
kenso status              # shows new/modified/deleted files since last optimize
kenso ingest ./docs --json    # current state of the index
```

If git is available, uses `git diff --name-only <last_sha>` for both source
code and documentation. If not, falls back to content hash comparison.

Categorizes changes:
- **New source code without docs:** needs new documentation
- **Modified source code with docs:** docs may need updating
- **Modified docs (manual edits):** need re-optimization
- **Deleted source files:** docs may be orphaned

### Step 1 — Present changes

```
Changes since last update (2026-03-15, sha: a3f7c2d):

  Source code:
    + src/domain/funds/NavCalculator.java         (new)
    ~ src/domain/orders/MatchingEngine.java       (modified)

  Documentation:
    ~ docs/domain/orders/matching-engine.md       (manually updated)
    ⚠ docs/domain/funds/  — no documentation for NavCalculator

  Proposed actions:
    1. Generate docs/knowledge/entities/nav-calculator.md      (new)
    2. Re-optimize docs/domain/orders/matching-engine.md       (manual changes)
    3. Re-analyze cross-links (new concept: NAV calculation)

  Estimated: 3 files · ~1 min

  Proceed?
```

### Step 2 — Apply updates

For new documentation: delegates to the appropriate generation workflow
(same as `/kenso:init` but only for the new files).

For modified documentation: delegates to `workflows/optimize-files.md`
targeting only the changed files.

### Step 3 — Cross-analysis

Runs `workflows/cross-analysis.md` on the full map but scoped — only
proposes changes for files in the change set and their direct neighbors
in the document graph.

### Step 4 — Re-index + report

```bash
kenso ingest ./docs --json    # re-index everything
```

```
📊 Update complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                     Before    After
Score:                 84        94

Files updated:          3
  Generated:            1 (nav-calculator.md)
  Re-optimized:         1 (matching-engine.md)
  Cross-links added:    4

State saved: sha e7b2f1a
```

### Scope control

For large projects, the command only processes the change set. It does NOT
re-optimize all 200 files when only 5 changed. The cross-analysis reads the
full map (lightweight — just the fichas) but only proposes changes for
affected files.

### Files involved

| Type | Files |
|------|-------|
| Skill | `skills/kenso-update/SKILL.md` |
| Slash command | `.claude/commands/kenso/update.md` (thin wrapper, Claude Code only) |
| Workflows | Reuses `workflows/generate-*.md`, `workflows/optimize-files.md`, `workflows/cross-analysis.md` |
| Agents | Reuses `agents/kenso:generator.md`, `agents/kenso:optimizer.md`, `agents/kenso:analyst.md` |
| CLI | `kenso status`, `kenso ingest --json`, `kenso lint --file --json`, `kenso apply` |

---

## `/kenso:ask`

### Purpose

Direct question about the project. The user asks, kenso finds the relevant
documents, the agent synthesizes a concise answer with source citations.

### Preconditions

- kenso index exists (`kenso ingest` has been run)

### User experience

```
User: /kenso:ask How does the settlement process handle failed trades?

Agent:
  When a settlement fails due to insufficient securities or cash shortfall,
  the system triggers an automatic buy-in procedure and reports to CNMV
  within 24 hours.

  The failed settlement handling is governed by rules BR-045 and BR-046:
  - BR-045: Automatic buy-in initiation after T+4
  - BR-046: CNMV notification within 24h of failure detection

  The settlement job (SETTLEMENT_RECONCILIATION) runs daily at 08:00 and
  checks for failed settlements from the previous business day.

  Sources:
  - docs/knowledge/entities/settlement.md § Failed Settlement Handling
  - docs/knowledge/rules/settlement-rules.md § BR-045, BR-046
  - docs/knowledge/jobs/settlement-reconciliation.md
```

### Flow

This is a single-layer command — no workflow or agent delegation needed.

```
1. Parse the user's question
2. Classify query type (entity, process, rule, implementation, integration...)
3. Build search terms from the question
4. Run kenso search (may run multiple searches for complex questions)
5. Read full content of top results
6. Synthesize answer citing sources
```

### Step 1-3 — Query classification and search

The command classifies the question to improve search precision:

| Classification | Search strategy |
|----------------|----------------|
| Entity query ("what is X?") | Search for entity name, filter by entities category |
| Process query ("how does X work?") | Search for process terms, also search workflows |
| Rule query ("what are the rules for X?") | Search in rules category |
| Implementation query ("how is X implemented?") | Search codebase + knowledge |
| Integration query ("how does X connect to Y?") | Search integrations |
| General / unclear | Broad search, no category filter |

**CLI invoked:**
```bash
kenso search "<terms>" --json --limit 5
# may run additional searches if first results are insufficient
kenso search "<refined terms>" --json --category <cat> --limit 5
```

### Step 4-5 — Read and synthesize

For each relevant result, the command reads the full document (or the specific
section if the chunk title identifies it). Then synthesizes an answer that:

- Answers the question directly (lead with the answer, not the context)
- Cites specific documents and sections
- Mentions related documents the user might want to explore
- Stays concise — this is not `/kenso:brainstorm`

### Skill description (all runtimes)

For implicit activation in Codex, the SKILL.md description should be:

> "Answer questions about the project using the kenso knowledge base. Use when
> the user asks about how something works, what the rules are, where something
> is implemented, or any question that could be answered by the project's
> documentation. Do not use for creating tasks, brainstorming, or explaining
> specific code snippets."

### Files involved

| Type | Files |
|------|-------|
| Skill | `skills/kenso-ask/SKILL.md` |
| Slash command | `.claude/commands/kenso/ask.md` (thin wrapper, Claude Code only) |
| CLI | `kenso search --json` |

---

## `/kenso:define`

### Purpose

Define a task or ticket with full project context. Searches the KB for
everything relevant to the requested work and produces a structured task
specification.

### Preconditions

- kenso index exists

### User experience

```
User: /kenso:define Add support for investment funds in the matching engine

Agent:
  ## Task: Add Investment Fund Support to Matching Engine

  ### Context
  The matching engine currently handles equity instruments only
  (docs/knowledge/entities/matching-engine.md). Investment funds are a new
  instrument type being introduced (docs/knowledge/entities/fund.md) with
  NAV-based pricing instead of order-book matching.

  ### Affected entities
  - MatchingEngine — needs new matching mode for NAV-based instruments
  - Fund — new entity (partially documented)
  - Order — needs fund-specific order type (subscription/redemption)
  - Instrument — needs fund instrument subtype

  ### Affected files
  - src/domain/matching/MatchingEngine.java
  - src/domain/orders/OrderValidator.java
  - src/api/v2/OrderController.java
  - (tests in src/test/domain/matching/)

  ### Applicable rules
  - BR-012: Instrument type determines matching mode
  - BR-034: NAV orders can only execute at published NAV price
  - BR-035: Fund subscription window validation

  ### Integration points
  - BIA: fund settlement follows different flow (T+3 vs T+2)
  - Aletheia: KYC check required for fund subscriptions (new check type)

  ### Acceptance criteria
  - [ ] Fund orders are matched at NAV price, not via order book
  - [ ] Subscription/redemption order types are validated
  - [ ] Settlement is routed to fund settlement flow (T+3)
  - [ ] KYC check is triggered for new fund subscribers

  ### Open questions
  - Does the matching engine need to support partial fund fills?
  - How is the NAV price fed into the system? (manual vs API)

  Sources: matching-engine.md, fund.md, order-rules.md, bia.md
```

### Flow

Same pattern as `/kenso:ask` but with broader search and different synthesis:

```
1. Parse the task description
2. Extract key concepts (entities, actions, modules mentioned)
3. Run multiple searches: entities, rules, integrations, codebase
4. Read full content of all relevant results
5. Synthesize structured task spec
```

### Search strategy

`/kenso:define` runs more searches than `/kenso:ask` because it needs
comprehensive context, not just a targeted answer:

```bash
# Entity search
kenso search "matching engine fund" --json --limit 5

# Rules search
kenso search "matching rules order validation fund" --json --category rules --limit 5

# Integration search
kenso search "fund settlement BIA" --json --category integrations --limit 3

# Codebase search
kenso search "MatchingEngine OrderValidator" --json --category codebase --limit 3
```

### Synthesis rules

The task spec must include:
- **Context:** what exists today, grounded in docs (not guessed)
- **Affected entities:** only entities found in the KB
- **Affected files:** from codebase docs (structure.md, architecture.md)
- **Applicable rules:** with BR-IDs from the KB
- **Integration points:** if async integrations are affected
- **Acceptance criteria:** derived from rules and existing patterns
- **Open questions:** things the KB doesn't answer

The agent never invents rules, entities, or file paths. Everything comes
from the KB or is explicitly marked as an open question.

### Skill description (all runtimes)

> "Define a task or ticket with full project context from the kenso knowledge
> base. Use when the user wants to plan work, create a ticket, spec a feature,
> or scope a task. Searches for affected entities, rules, integrations, and
> code locations. Do not use for answering questions or brainstorming."

### Files involved

| Type | Files |
|------|-------|
| Skill | `skills/kenso-define/SKILL.md` |
| Slash command | `.claude/commands/kenso/define.md` (thin wrapper, Claude Code only) |
| CLI | `kenso search --json` (multiple calls) |

---

## `/kenso:brainstorm`

### Purpose

Open exploration informed by the KB. The user describes a direction and the
agent generates ideas, trade-offs, and connections grounded in documented
architecture and constraints.

### Preconditions

- kenso index exists

### User experience

```
User: /kenso:brainstorm How could we reduce matching engine latency?

Agent:
  Based on the current architecture, here are approaches worth exploring:

  **1. Pre-validation cache**
  The matching engine currently validates every order against 12 rules
  (BR-001 through BR-012) on each submission. Rules BR-001 to BR-005 depend
  only on instrument state, which changes infrequently. Caching instrument
  validation results could skip 5 rule checks per order.

  Trade-off: cache invalidation when instrument state changes (halt, suspend).
  The INSTRUMENT_STATE_CHANGE job would need to flush the cache.

  **2. Batch matching windows**
  Currently orders are matched individually on arrival. For high-volume
  instruments, batching orders into 100ms windows and matching the batch
  would reduce lock contention on the order book.

  Trade-off: adds latency for individual orders (up to 100ms). Conflicts
  with BR-009 (price-time priority must be respected within the batch).

  **3. Separate the settlement trigger**
  The matching engine currently calls the settlement service synchronously
  after a trade. Moving settlement to an async event (BIA already supports
  this pattern — see bia.md § outbound messages) would free the matching
  thread immediately.

  Trade-off: trade confirmation to the user is delayed until settlement
  confirmation arrives. Need to handle the "trade executed but settlement
  pending" state in the UI.

  Each approach has different risk/reward profiles. Want me to /kenso:define
  any of these as a task?
```

### Flow

```
1. Parse the exploration topic
2. Run broad searches across multiple categories
3. Read relevant documents for context
4. Generate ideas grounded in documented architecture
5. For each idea, identify trade-offs and constraints from the KB
6. Suggest next steps (define as task, explore further, etc.)
```

### Search strategy

Broader than `/kenso:ask`, more exploratory:

```bash
kenso search "matching engine performance latency" --json --limit 10
kenso search "order processing pipeline" --json --limit 5
kenso search "matching integration settlement" --json --limit 5
```

### Synthesis rules

The agent:
- Generates 2-5 ideas (not 10 shallow ones)
- Grounds each idea in specific documents and entities
- Identifies constraints and trade-offs from rules and architecture docs
- Connects ideas to existing patterns in the codebase
- Suggests concrete next steps
- Does NOT generate generic advice — every suggestion references the KB

### Skill description (all runtimes)

> "Brainstorm ideas and explore possibilities using the kenso knowledge base.
> Use when the user wants to think through approaches, explore alternatives,
> or generate ideas grounded in their project's architecture and constraints.
> Do not use for direct questions or task definitions."

### Files involved

| Type | Files |
|------|-------|
| Skill | `skills/kenso-brainstorm/SKILL.md` |
| Slash command | `.claude/commands/kenso/brainstorm.md` (thin wrapper, Claude Code only) |
| CLI | `kenso search --json` (multiple calls) |

---

## `/kenso:explain`

### Purpose

Explain code with business context. The user points to a piece of code and
the agent explains not just what it does, but why it exists — connecting
implementation to rules, decisions, and domain concepts.

### Preconditions

- kenso index exists
- The user references a file, function, or code snippet

### User experience

```
User: /kenso:explain Why does MatchingEngine.java check isHalted() before processing?

Agent:
  The isHalted() check implements rule BR-017 (Market Halt Enforcement).

  When the CNMV orders a trading suspension on an instrument, its
  tradingStatus changes to HALTED. This can happen two ways:
  - Manual: via backoffice (docs/knowledge/actions/halt-instrument.md)
  - Automatic: via MARKET_SURVEILLANCE job
    (docs/knowledge/jobs/market-surveillance.md)

  If the matching engine processed orders on a halted instrument,
  Portfolio SE would violate Article 32 of RD 21/2017.

  The halt state is checked at two points:
  1. Order submission (OrderValidator.java — preventive)
  2. Match execution (MatchingEngine.java — defensive, handles race condition
     where halt arrives between validation and matching)

  This dual-check pattern is documented as a concern in
  docs/codebase/concerns.md § Race Conditions in State Transitions.

  Related:
  - Rule: docs/knowledge/rules/order-rules.md § BR-017
  - Entity: docs/knowledge/entities/instrument.md § lifecycle
  - Decision: docs/decisions/adr/007-halt-propagation.md
```

### Flow

```
1. Identify the code reference (file, function, snippet, or concept)
2. Extract identifiers: class names, method names, field names, patterns
3. Search for business context: rules, entities, decisions, concerns
4. Search for implementation context: codebase docs, conventions
5. Synthesize explanation connecting code to business rationale
```

### Search strategy

Dual-track — business context and implementation context:

```bash
# Business context
kenso search "isHalted halt instrument trading suspension" --json --limit 5
kenso search "halt rules BR" --json --category rules --limit 3

# Implementation context
kenso search "MatchingEngine order validation" --json --category codebase --limit 3
kenso search "race condition state transition" --json --limit 3
```

### Synthesis rules

The agent:
- Leads with the **why** (business rule, regulatory requirement, decision)
- Then explains the **how** (implementation pattern, where it's enforced)
- Connects to related code if the pattern appears in multiple places
- References decisions (ADRs) if they explain design choices
- Flags concerns if the code touches a known fragile area
- Never explains obvious code mechanics — focuses on business rationale

### Skill description (all runtimes)

> "Explain code using business context from the kenso knowledge base. Use when
> the user asks why code exists, what a check enforces, why a pattern was
> chosen, or how code connects to business rules. Do not use for general
> questions or task definitions."

### Files involved

| Type | Files |
|------|-------|
| Skill | `skills/kenso-explain/SKILL.md` |
| Slash command | `.claude/commands/kenso/explain.md` (thin wrapper, Claude Code only) |
| CLI | `kenso search --json` (multiple calls) |

---

## `/kenso:refine`

**Status:** Future (depends on Phase 5 — `/kenso:define`)

### Purpose

Refine a task definition through a panel of virtual domain experts. After
`/kenso:define` produces an initial spec, `/kenso:refine` has it reviewed
by multiple specialized perspectives that each consult the KB for their
domain.

### Preconditions

- kenso index exists
- A task definition exists (from `/kenso:define` or provided by the user)

### User experience

```
User: /kenso:refine [pastes or references a task spec]

Agent:
  Refining task with expert panel...

  🔒 Security review
  The task adds a new order type for fund subscriptions. The KYC check
  for fund subscribers (mentioned in acceptance criteria) needs to
  specify which verification level is required. Per BR-089 (KYC Level
  by Instrument Risk), funds classified as complex instruments require
  Enhanced Due Diligence (EDD), not standard KYC.

  Add to acceptance criteria:
  - [ ] Fund subscription triggers EDD-level KYC (not standard)
  - [ ] KYC rejection blocks the subscription order

  ⚙️ Infrastructure review
  The matching engine currently runs as a single instance. Adding a
  NAV-based matching mode increases the code path complexity. Per
  docs/codebase/concerns.md § Matching Engine Single Point of Failure,
  this is already a known concern.

  Suggestion: implement the NAV matching as a separate service or at
  minimum a separate strategy class, so it can be deployed/scaled
  independently.

  🎨 UX review
  The "trade executed but settlement pending" state (trade-off #3 from
  the brainstorm) needs a frontend representation. Currently the order
  status flow shows: Pending → Executed → Settled. A new intermediate
  state "Executed (settling)" is needed.

  Add to acceptance criteria:
  - [ ] Frontend shows "Settling" status for fund trades
  - [ ] User receives notification when fund settlement completes

  📋 Operations review
  Fund settlement at T+3 means the SETTLEMENT_RECONCILIATION job
  (currently runs at T+2 + 1 business day) needs a separate schedule
  for fund trades. The daily settlement report (transaction-report-xml)
  needs to include fund settlements.

  Add to acceptance criteria:
  - [ ] Settlement reconciliation handles T+3 fund trades
  - [ ] Transaction report XML includes fund settlement entries

  ---

  Refined task spec: [updated version with all additions]
```

### Flow

```
1. Parse or load the task definition
2. Extract key concepts (entities, integrations, areas of impact)
3. For each expert perspective:
   a. Search the KB for their domain (security → rules, infra → codebase, etc.)
   b. Analyze the task through their lens
   c. Identify gaps, risks, or additions
4. Compile all expert inputs
5. Produce a refined task spec with additions clearly marked
```

### Expert perspectives

Each perspective has a search focus and analysis lens:

| Expert | Search focus | Analysis lens |
|--------|-------------|---------------|
| Security | Rules (BR-*), compliance, authentication, authorization | What security constraints apply? What validations are missing? |
| Infrastructure | Codebase (architecture, concerns, stack), deployment | Scale impact? Single points of failure? Deployment concerns? |
| UX/UI | Frontend codebase, workflows, views | User-facing state changes? New UI states needed? Notifications? |
| Operations | Jobs, reports, integrations, monitoring | Operational impact? Job schedule changes? Report changes? |
| QA | Testing docs, workflows, edge cases | What test scenarios are needed? What edge cases exist? |
| Domain | Entities, rules, domain model | Business rule consistency? Entity model changes? |

The command doesn't always invoke all experts. It selects 3-5 relevant
perspectives based on what the task touches:
- Task touches matching engine → infra, security, operations, domain
- Task touches frontend → UX, QA
- Task touches integrations → infra, operations, security

### Architecture

This is the first consultation command that uses the **agent layer**. Each
expert perspective could be a separate agent spawn (for context freshness)
or sequential analysis in the main context (simpler, less token-efficient).

For the initial implementation, sequential analysis in the main context is
sufficient. If context becomes a problem with complex tasks, refactor to
spawn per-expert agents.

### Skill description (all runtimes)

> "Refine a task definition through a panel of domain experts using the kenso
> knowledge base. Use after /kenso:define to get security, infrastructure, UX,
> operations, and QA perspectives on a task spec. Do not use without an
> existing task definition."

### Files involved

| Type | Files |
|------|-------|
| Skill | `skills/kenso-refine/SKILL.md` |
| Slash command | `.claude/commands/kenso/refine.md` (thin wrapper, Claude Code only) |
| Agents | (future) `agents/kenso:refine-panel.md` or individual expert agents |
| CLI | `kenso search --json` (multiple calls per expert) |

---

## Shared patterns across all commands

### Error handling

Every command handles these cases gracefully:

- **No index:** "No kenso index found. Run `kenso ingest ./docs` first, or
  use `/kenso:init` to set up your knowledge base."
- **Empty results:** "No relevant documents found for this query. The KB may
  not cover this topic yet." (never hallucinate an answer)
- **Partial results:** Synthesize from what's available, note what's missing.

### Source citation

All consultation commands cite sources. Citation format:

```
docs/knowledge/entities/settlement.md § Failed Settlement Handling
```

The `§` symbol followed by the section name points the user to the specific
chunk, not just the file.

### Category filtering

When a command knows the query type, it passes `--category` to `kenso search`
to improve precision. Categories come from the directory structure (codebase,
domain, entities, rules, etc.).

### Multi-search pattern

Complex queries often need multiple searches. The pattern is:

```bash
# Broad search first
kenso search "<main terms>" --json --limit 5

# If results are insufficient or too broad, refine:
kenso search "<specific terms>" --json --category <cat> --limit 5

# If the topic spans multiple areas:
kenso search "<term A>" --json --limit 3
kenso search "<term B>" --json --limit 3
# Merge results, deduplicate by document path
```

Commands should run the minimum number of searches needed. `/kenso:ask` often
needs just 1-2 searches. `/kenso:define` typically needs 4-6. `/kenso:refine`
may need 10+ across all expert perspectives.
