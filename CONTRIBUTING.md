# Contributing to kenso

Thanks for your interest in contributing to kenso! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/fvena/kenso.git
cd kenso
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,yaml]"
pre-commit install --hook-type commit-msg
```

The `-e` (editable) install means the `kenso` command now points to your local source code. Any change you save is immediately available — no reinstall needed.

## Try Your Changes

Create a small test knowledge base to work with:

```bash
mkdir -p /tmp/kenso-dev/docs
cat > /tmp/kenso-dev/docs/example.md << 'EOF'
---
title: Deployment Pipeline
category: infrastructure
tags: deploy, CI/CD, rollback
---

# Deployment Pipeline

The deployment pipeline automates building, testing, and releasing code.

## Build Stage

The build stage compiles the application and runs unit tests.

## Deploy Stage

The deploy stage pushes artifacts to production using blue-green deployment.
EOF
```

Then test the full workflow:

```bash
kenso ingest /tmp/kenso-dev/docs/   # index the files
kenso search "deployment"           # test search
kenso search "rollback"             # test tag matching
kenso stats                         # check index contents
```

For changes to search or ranking, run the eval harness:

```bash
python tests/eval/eval_harness.py
python tests/eval/eval_harness.py --compare baseline
```

## Running the Test Suite

```bash
pytest                                          # all tests
pytest tests/test_ingest.py                     # single module
pytest tests/test_backend.py -k "test_search"   # single test
pytest --cov=kenso --cov-report=term-missing    # with coverage
```

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and import sorting.

```bash
ruff check src/ tests/       # lint
ruff check src/ tests/ --fix # lint and auto-fix
```

Conventions: 99 character line length, Python 3.11+, `from __future__ import annotations` in all modules.

## Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/) to automate versioning and changelog generation. A pre-commit hook validates the format automatically.

Format: `<type>(<scope>): <description>`

| Type | When to use |
|------|-------------|
| `feat` | New feature (minor version bump) |
| `fix` | Bug fix (patch version bump) |
| `perf` | Performance improvement (patch bump) |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `ci` | CI/CD changes |
| `chore` | Maintenance tasks |

Examples:

```
feat(search): add prefix matching for single-word queries
fix(ingest): handle empty frontmatter blocks without crashing
docs: add editor integration examples for VS Code
test(backend): add unit tests for deduplication logic
```

## Pull Requests

1. Fork the repository and create a feature branch from `main`
2. Write tests for any new functionality
3. Ensure all tests pass and linting is clean
4. Keep commits atomic — one logical change per commit
5. Write a clear PR description explaining what and why

Checklist:

- [ ] Tests added or updated
- [ ] `pytest` passes
- [ ] `ruff check src/ tests/` passes
- [ ] Commit messages follow Conventional Commits
- [ ] Documentation updated if needed

## Project Structure

```
src/kenso/
├── __init__.py      # Version
├── __main__.py      # python -m kenso entry point
├── backend.py       # SQLite FTS5 backend, search, CRUD
├── cli.py           # Command-line interface
├── config.py        # Environment-based configuration
├── ingest.py        # Markdown parsing, chunking, ingestion
├── schema.py        # SQLite DDL
└── server.py        # FastMCP server and tool definitions

tests/
├── test_config.py   # Configuration tests
├── test_backend.py  # Backend search and CRUD tests
├── test_ingest.py   # Parsing and chunking tests
└── eval/            # Search quality benchmarks
```

## Reporting Bugs

Open an issue with: kenso version (`kenso --version`), Python version, steps to reproduce, and expected vs. actual behavior.

## Questions?

Open a [Discussion](https://github.com/fvena/kenso/discussions) or an issue labeled `question`.
