"""CLI: serve, ingest, search, stats, lint, install."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections import Counter

from kenso import __version__
from kenso.ui import (
    Style,
    cascade_label,
    glyph,
    header,
    human_size,
    next_step,
    output,
    relevance_label,
    rule_line,
    severity_glyph,
    summary,
    terminal_snippet,
)

__all__ = ["main"]

log = logging.getLogger("kenso")

_MAX_FILE_LIST = 20  # collapse file list when more than this many files


def _db_display(args: argparse.Namespace, config) -> str | None:
    """Return db path string only when a non-default db was chosen."""
    if getattr(args, "db", None):
        return config.database_url
    if os.environ.get("KENSO_DATABASE_URL"):
        return config.database_url
    return None


# ── serve ──────────────────────────────────────────────────────────


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the MCP server."""
    from kenso.config import KensoConfig
    from kenso.server import mcp

    config = KensoConfig.from_env(db_override=getattr(args, "db", None))
    log.debug("using %s (%s)", config.database_url, config.database_source)

    transport = config.transport
    if transport in ("sse", "streamable-http"):
        mcp.settings.host = config.host
        mcp.settings.port = int(config.port)

    mcp.run(transport=transport)  # type: ignore[arg-type]


# ── ingest ─────────────────────────────────────────────────────────


def cmd_ingest(args: argparse.Namespace) -> None:
    """Ingest markdown files."""
    from kenso.config import KensoConfig
    from kenso.ingest import ingest_path

    config = KensoConfig.from_env(
        db_override=getattr(args, "db", None),
        create_if_missing=True,
    )
    log.debug("using %s (%s)", config.database_url, config.database_source)

    async def _run():
        results = await ingest_path(config, args.path)
        counts = Counter(r.action for r in results)
        total_chunks = sum(r.chunks for r in results)

        if args.json:
            _print_ingest_json(args.path, results, counts, total_chunks)
            return

        # Header
        header(
            f"indexing {len(results)} documents",
            db_path=_db_display(args, config),
        )

        # File list (show once, collapse if > _MAX_FILE_LIST)
        status_map = {
            "ingested": (Style.GREEN, glyph["ok"]),
            "unchanged": (Style.DIM, glyph["dash"]),
            "skipped": (Style.DIM, glyph["skip"]),
            "error": (Style.RED, glyph["fail"]),
            "removed": (Style.RED, glyph["removed"]),
        }
        shown = 0
        for r in results:
            color, sym = status_map.get(r.action, ("", "?"))
            chunk_label = f"{r.chunks} chunk{'s' if r.chunks != 1 else ''}"
            line = f"{color}{sym}{Style.RESET} {r.path:<50} {Style.DIM}{chunk_label}{Style.RESET}"
            if r.detail:
                line += f" {Style.DIM}[{r.detail}]{Style.RESET}"
            if shown < _MAX_FILE_LIST:
                output(line)
            shown += 1
        if shown > _MAX_FILE_LIST:
            output(f"{Style.DIM}... and {shown - _MAX_FILE_LIST} more{Style.RESET}")

        # Summary line
        parts = []
        parts.append(f"{len(results)} files")
        parts.append(f"{counts.get('ingested', 0)} ingested")
        parts.append(f"{counts.get('unchanged', 0)} unchanged")
        parts.append(f"{total_chunks} chunks")
        summary(" {dot} ".format(dot=glyph["dot"]).join(parts))

        # Lint quality section
        has_indexable = any(r.action in ("ingested", "unchanged") for r in results)
        if has_indexable:
            try:
                from kenso.lint import lint_path

                chunk_size = int(os.environ.get("KENSO_CHUNK_SIZE", "4000"))
                lint_result = lint_path(args.path, chunk_size=chunk_size)
                _print_ingest_quality(lint_result)
            except Exception:
                log.debug("lint summary failed", exc_info=True)
                output(
                    f"\n{Style.YELLOW}Warning: Could not generate quality summary.{Style.RESET}"
                )

    asyncio.run(_run())


def _print_ingest_quality(lint_result) -> None:
    """Print the quality score section after ingest."""
    from kenso.lint import _IMPACT, _RULE_LABELS

    output(f"\nQuality score: {lint_result.score}/100")

    # Collect violation counts per rule
    rule_counts: dict[str, int] = {}
    rule_severity: dict[str, str] = {}
    for fr in lint_result.file_results:
        seen: set[str] = set()
        for v in fr.violations:
            if v.rule not in seen:
                rule_counts[v.rule] = rule_counts.get(v.rule, 0) + 1
                rule_severity[v.rule] = v.severity
                seen.add(v.rule)

    if rule_counts:
        sorted_rules = sorted(
            rule_counts.keys(),
            key=lambda r: (-_IMPACT.get(r, 0), r),
        )
        for rule in sorted_rules:
            label = _RULE_LABELS.get(rule, rule)
            count = rule_counts[rule]
            impact = _IMPACT.get(rule, 0)
            impact_str = f"+{impact}%" if impact else ""
            sev = rule_severity.get(rule, "warning")
            sg = severity_glyph(sev)
            count_str = f"{count} file{'s' if count != 1 else ''}"
            output(f"{sg} {label:<40} {count_str:>8} {impact_str:>5}")

    files_with_issues = sum(1 for fr in lint_result.file_results if fr.violations)
    if files_with_issues:
        output(f"{files_with_issues} files with issues {glyph['dot']} ", end="")
        next_step("kenso lint --detail")


def _print_ingest_json(
    path: str,
    results: list,
    counts: Counter,
    total_chunks: int,
) -> None:
    """Print ingest + lint results as a single JSON object to stdout."""
    files_list = []
    for r in results:
        entry: dict = {
            "path": r.path,
            "status": r.action,
            "chunks": r.chunks,
        }
        if r.title is not None:
            entry["title"] = r.title
        if r.category is not None:
            entry["category"] = r.category
        files_list.append(entry)

    ingest_data = {
        "path": path,
        "total_files": len(results),
        "ingested": counts.get("ingested", 0),
        "unchanged": counts.get("unchanged", 0),
        "skipped": counts.get("skipped", 0),
        "removed": counts.get("removed", 0),
        "errors": counts.get("error", 0),
        "total_chunks": total_chunks,
        "files": files_list,
    }

    # Build lint data using the same schema as `kenso lint --json`
    lint_data = None
    has_indexable = any(r.action in ("ingested", "unchanged") for r in results)
    if has_indexable:
        try:
            from kenso.lint import format_json as lint_format_json
            from kenso.lint import lint_path

            chunk_size = int(os.environ.get("KENSO_CHUNK_SIZE", "4000"))
            lint_result = lint_path(path, chunk_size=chunk_size)
            lint_data = json.loads(lint_format_json(lint_result))
        except Exception:
            log.debug("lint JSON failed", exc_info=True)

    result: dict = {"ingest": ingest_data}
    if lint_data is not None:
        result["lint"] = lint_data

    print(json.dumps(result, indent=2))


# ── search ─────────────────────────────────────────────────────────


def cmd_search(args: argparse.Namespace) -> None:
    """Search documents."""
    from kenso.backend import Backend
    from kenso.config import KensoConfig

    config = KensoConfig.from_env(db_override=getattr(args, "db", None))
    log.debug("using %s (%s)", config.database_url, config.database_source)

    # Fail early if the database doesn't exist (search is read-only)
    if config.database_url and config.database_url != ":memory:":
        from pathlib import Path

        db_path = Path(config.database_url)
        if not db_path.is_file():
            output(
                f"{Style.RED}Error: Database not found at {config.database_url}{Style.RESET}\n"
                f"Run {Style.BOLD}kenso ingest{Style.RESET} first."
            )
            sys.exit(1)

    async def _run():
        backend = Backend(config)
        await backend.startup()
        try:
            results = await backend.search(
                args.query,
                limit=args.limit,
                category=getattr(args, "category", None),
            )

            if args.json:
                _print_search_json(args.query, results, config)
                return

            if not results:
                header("0 results for " + f'"{args.query}"', db_path=_db_display(args, config))
                output("No results.")
            else:
                header(
                    f'{len(results)} results for "{args.query}"',
                    db_path=_db_display(args, config),
                )
                for r in results:
                    score = f"{r['score']:.2f}"
                    stage = r.get("cascade_stage", "")
                    rel = r.get("relevance", "low")

                    stage_str = f"  {cascade_label(stage)}" if stage else ""
                    rel_str = f"  {relevance_label(rel)}" if rel else ""

                    output(
                        f"{Style.BOLD}{score}{Style.RESET}  {r['file_path']}{stage_str}{rel_str}"
                    )

                    # Section path / title
                    section = r.get("section_path", "")
                    title = r.get("title", "")
                    if section:
                        output(f"      {Style.DIM}{section}{Style.RESET}")
                    elif title:
                        output(f"      {Style.DIM}{title}{Style.RESET}")

                    # Highlight snippet
                    if r.get("highlight"):
                        snippet = terminal_snippet(r["highlight"])
                        output(f"      {snippet}")

                    output()  # blank line between results
        finally:
            await backend.shutdown()

    asyncio.run(_run())


def _print_search_json(query: str, results: list[dict], config) -> None:
    """Print search results as a single JSON object to stdout."""
    from kenso.server import _build_snippet, _detect_match_source

    preview = config.content_preview_chars
    items = []
    for r in results:
        match_source = _detect_match_source(
            query,
            title=r["title"],
            tags=r.get("tags"),
            section_path=r.get("section_path", ""),
            category=r.get("category"),
        )
        item: dict = {
            "score": round(float(r["score"]), 4),
            "path": r["file_path"],
            "title": r["title"],
            "category": r.get("category"),
            "tags": r.get("tags", []),
            "preview": _build_snippet(r, query, match_source, preview),
            "snippet": r.get("highlight", ""),
            "related_count": r.get("related_count", 0),
            "cascade_stage": r.get("cascade_stage"),
            "relevance": r.get("relevance", "low"),
        }
        items.append(item)

    result = {
        "query": query,
        "total_results": len(items),
        "results": items,
    }
    if results and results[0].get("corrected_query"):
        result["corrected_query"] = results[0]["corrected_query"]

    print(json.dumps(result, indent=2))


# ── stats ──────────────────────────────────────────────────────────


def cmd_stats(args: argparse.Namespace) -> None:
    """Show database statistics."""
    from kenso.backend import Backend
    from kenso.config import KensoConfig

    config = KensoConfig.from_env(db_override=getattr(args, "db", None))
    log.debug("using %s (%s)", config.database_url, config.database_source)

    # Fail early if the database doesn't exist (stats is read-only)
    if config.database_url and config.database_url != ":memory:":
        from pathlib import Path

        db_path = Path(config.database_url)
        if not db_path.is_file():
            output(
                f"{Style.RED}Error: Database not found at {config.database_url}{Style.RESET}\n"
                f"Run {Style.BOLD}kenso ingest{Style.RESET} first."
            )
            sys.exit(1)

    async def _run():
        backend = Backend(config)
        await backend.startup()
        try:
            s = await backend.stats()

            header("stats", db_path=_db_display(args, config))
            output(rule_line(45))
            output(f"  {'Documents:':<14} {s['docs']:>8}")
            output(f"  {'Chunks:':<14} {s['chunks']:>8}")
            output(f"  {'Size:':<14} {human_size(s['content_bytes']):>8}")
            output(f"  {'Links:':<14} {s['links'] or 0:>8}")
            output(rule_line(45))

            for cat in s["categories"]:
                name = cat["cat"] or "(none)"
                output(f"  {name:<20} {cat['docs']:>4} docs, {cat['chunks']:>4} chunks")
            output()
        finally:
            await backend.shutdown()

    asyncio.run(_run())


# ── lint ───────────────────────────────────────────────────────────


def cmd_lint(args: argparse.Namespace) -> None:
    """Lint markdown files for retrieval quality issues."""
    from kenso.lint import format_detail, format_json, format_summary, lint_path

    chunk_size = int(os.environ.get("KENSO_CHUNK_SIZE", "4000"))
    result = lint_path(args.path, chunk_size=chunk_size)

    if args.json:
        print(format_json(result))
    elif args.detail:
        output(format_detail(result))
    else:
        output(format_summary(result))

    sys.exit(1 if result.errors > 0 else 0)


# ── install ────────────────────────────────────────────────────────


def cmd_install(args: argparse.Namespace) -> None:
    """Install kenso commands into LLM runtime directories."""
    from kenso.install import find_project_root, install_claude, install_codex

    root = find_project_root()
    if root is None:
        output(
            f"{Style.RED}Error: could not find project root.{Style.RESET} "
            "Run from inside a project directory (one with .git/, pyproject.toml, etc.)."
        )
        sys.exit(1)

    do_claude = args.claude
    do_codex = args.codex
    do_all = args.all

    if do_all:
        do_claude = do_codex = True

    # Auto-detect if no flags given
    if not do_claude and not do_codex:
        has_claude = (root / ".claude").is_dir()
        has_codex = (root / ".codex").is_dir()
        if has_claude:
            do_claude = True
        if has_codex:
            do_codex = True
        if not do_claude and not do_codex:
            output(
                "No runtime detected. Use --claude, --codex, or --all to "
                "specify which runtime to install for."
            )
            sys.exit(1)

    header("install")

    if do_claude:
        lines = install_claude(root)
        for line in lines:
            output(line)

    if do_codex:
        if do_claude:
            output()
        lines = install_codex(root)
        for line in lines:
            output(line)


# ── Logging & main ─────────────────────────────────────────────────


def _configure_logging(log_level: str = "WARNING") -> None:
    """Configure logging based on level string."""
    level = getattr(logging, log_level.upper(), logging.WARNING)
    logging.basicConfig(level=level, force=True)


def main() -> None:
    # Default to WARNING; only DEBUG when explicitly requested
    env_level = os.environ.get("KENSO_LOG_LEVEL", "WARNING")
    _configure_logging(env_level)

    parser = argparse.ArgumentParser(
        prog="kenso", description="Markdown knowledge base for AI agents"
    )
    parser.add_argument("--version", action="version", version=f"kenso {__version__}")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (equivalent to KENSO_LOG_LEVEL=DEBUG)",
    )
    sub = parser.add_subparsers(dest="command")

    _db_help = "Database path (overrides KENSO_DATABASE_URL and auto-detection)"

    # serve
    p = sub.add_parser("serve", help="Start MCP server")
    p.add_argument("--db", type=str, default=None, help=_db_help)

    # ingest
    p = sub.add_parser("ingest", help="Ingest markdown files")
    p.add_argument("path", help="File or directory to ingest")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--db", type=str, default=None, help=_db_help)

    # search
    p = sub.add_parser("search", help="Search documents")
    p.add_argument("query", help="Search query")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--limit", type=int, default=5, help="Max results (default 5)")
    p.add_argument("--category", type=str, default=None, help="Filter by category")
    p.add_argument("--db", type=str, default=None, help=_db_help)

    # stats
    p = sub.add_parser("stats", help="Database statistics")
    p.add_argument("--db", type=str, default=None, help=_db_help)

    # lint
    p = sub.add_parser("lint", help="Lint markdown files for retrieval quality")
    p.add_argument("path", help="File or directory to lint")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--detail", action="store_true", help="Show per-file violations")
    group.add_argument("--json", action="store_true", help="Output as JSON")

    # install
    p = sub.add_parser("install", help="Install kenso commands for an LLM runtime")
    p.add_argument("--claude", action="store_true", help="Install for Claude Code")
    p.add_argument("--codex", action="store_true", help="Install for Codex CLI")
    p.add_argument("--all", action="store_true", help="Install for all supported runtimes")

    args = parser.parse_args()

    # Apply --debug flag
    if getattr(args, "debug", False):
        _configure_logging("DEBUG")

    if not args.command:
        parser.print_help()
        sys.exit(1)

    {
        "serve": cmd_serve,
        "ingest": cmd_ingest,
        "search": cmd_search,
        "stats": cmd_stats,
        "lint": cmd_lint,
        "install": cmd_install,
    }[args.command](args)
