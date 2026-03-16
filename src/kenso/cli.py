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

__all__ = ["main"]

log = logging.getLogger("kenso")


def _log_database(config) -> None:
    """Log which database is being used and why."""
    log.info("using %s (%s)", config.database_url, config.database_source)


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the MCP server."""
    from kenso.config import KensoConfig
    from kenso.server import mcp

    config = KensoConfig.from_env()
    _log_database(config)

    transport = config.transport
    if transport in ("sse", "streamable-http"):
        mcp.settings.host = config.host
        mcp.settings.port = int(config.port)

    mcp.run(transport=transport)  # type: ignore[arg-type]


def cmd_ingest(args: argparse.Namespace) -> None:
    """Ingest markdown files."""
    from kenso.config import KensoConfig
    from kenso.ingest import ingest_path

    config = KensoConfig.from_env()
    _log_database(config)

    # Ensure .kenso/ directory exists for local project databases
    if config.database_url and config.database_url.endswith(".kenso/docs.db"):
        os.makedirs(os.path.dirname(config.database_url), exist_ok=True)

    async def _run():
        results = await ingest_path(config, args.path)
        counts = Counter(r.action for r in results)
        total_chunks = sum(r.chunks for r in results)

        if args.json:
            _print_ingest_json(args.path, results, counts, total_chunks)
            return

        for r in results:
            status = {
                "ingested": "✓",
                "unchanged": "–",
                "skipped": "⊘",
                "error": "✗",
                "removed": "✕",
            }.get(r.action, "?")
            line = f"  {status} {r.path} ({r.chunks} chunks)"
            if r.detail:
                line += f" [{r.detail}]"
            print(line)

        print(
            f"\n  {len(results)} files: {counts.get('ingested', 0)} ingested, "
            f"{counts.get('unchanged', 0)} unchanged, "
            f"{counts.get('skipped', 0)} skipped, "
            f"{counts.get('removed', 0)} removed, "
            f"{counts.get('error', 0)} errors. "
            f"Total: {total_chunks} chunks."
        )

        if counts.get("unchanged", 0) > 0:
            print(
                "\n  Note: Unchanged files were not re-ingested. Re-ingest with"
                " updated content to enable compound term expansion for"
                " improved search."
            )

        # Append lint quality summary if there are indexable files
        has_indexable = any(r.action in ("ingested", "unchanged") for r in results)
        if has_indexable:
            try:
                from kenso.lint import format_ingest_summary, lint_path

                chunk_size = int(os.environ.get("KENSO_CHUNK_SIZE", "4000"))
                lint_result = lint_path(args.path, chunk_size=chunk_size)
                print(f"\n{format_ingest_summary(lint_result)}")
            except Exception:
                log.debug("lint summary failed", exc_info=True)
                print("\n  Warning: Could not generate quality summary.")

    asyncio.run(_run())


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

    output: dict = {"ingest": ingest_data}
    if lint_data is not None:
        output["lint"] = lint_data

    print(json.dumps(output, indent=2))


def cmd_search(args: argparse.Namespace) -> None:
    """Search documents."""
    from kenso.backend import Backend
    from kenso.config import KensoConfig

    config = KensoConfig.from_env()
    _log_database(config)

    async def _run():
        backend = Backend(config)
        await backend.startup()
        try:
            results = await backend.search(args.query, limit=5)
            if not results:
                print("  No results.")
            else:
                for r in results:
                    score = f"{r['score']:.3f}"
                    print(f"  [{score}] {r['file_path']}")
                    print(f"         {r['title']}")
                    if r.get("highlight"):
                        print(f"         {r['highlight']}")
                    print()
        finally:
            await backend.shutdown()

    asyncio.run(_run())


def cmd_stats(args: argparse.Namespace) -> None:
    """Show database statistics."""
    from kenso.backend import Backend
    from kenso.config import KensoConfig

    config = KensoConfig.from_env()
    _log_database(config)

    async def _run():
        backend = Backend(config)
        await backend.startup()
        try:
            s = await backend.stats()
            print("\n  kenso stats")
            print(f"  {'─' * 40}")
            print(f"  Documents: {s['docs']}")
            print(f"  Chunks:    {s['chunks']}")
            print(f"  Size:      {s['content_bytes']:,} bytes")
            print(f"  Links:     {s['links'] or 0}")
            print(f"  {'─' * 40}")
            for cat in s["categories"]:
                print(
                    f"    {cat['cat'] or '(none)':<20} {cat['docs']} docs, {cat['chunks']} chunks"
                )
            print()
        finally:
            await backend.shutdown()

    asyncio.run(_run())


def cmd_lint(args: argparse.Namespace) -> None:
    """Lint markdown files for retrieval quality issues."""
    from kenso.lint import format_detail, format_json, format_summary, lint_path

    chunk_size = int(os.environ.get("KENSO_CHUNK_SIZE", "4000"))
    result = lint_path(args.path, chunk_size=chunk_size)

    if args.json:
        print(format_json(result))
    elif args.detail:
        print(format_detail(result))
    else:
        print(format_summary(result))

    sys.exit(1 if result.errors > 0 else 0)


def cmd_install(args: argparse.Namespace) -> None:
    """Install kenso commands into LLM runtime directories."""
    from kenso.install import find_project_root, install_claude, install_codex

    root = find_project_root()
    if root is None:
        print(
            "Error: could not find project root. Run from inside a project "
            "directory (one with .git/, pyproject.toml, etc.)."
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
            print(
                "No runtime detected. Use --claude, --codex, or --all to "
                "specify which runtime to install for."
            )
            sys.exit(1)

    if do_claude:
        lines = install_claude(root)
        print("\n".join(lines))

    if do_codex:
        if do_claude:
            print()
        lines = install_codex(root)
        print("\n".join(lines))


def _configure_logging(log_level: str = "INFO") -> None:
    """Configure logging based on level string."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(level=level)


def main() -> None:
    _configure_logging(os.environ.get("KENSO_LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(
        prog="kenso", description="Markdown knowledge base for AI agents"
    )
    parser.add_argument("--version", action="version", version=f"kenso {__version__}")
    sub = parser.add_subparsers(dest="command")

    # serve
    sub.add_parser("serve", help="Start MCP server")

    # ingest
    p = sub.add_parser("ingest", help="Ingest markdown files")
    p.add_argument("path", help="File or directory to ingest")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # search
    p = sub.add_parser("search", help="Search documents")
    p.add_argument("query", help="Search query")

    # stats
    sub.add_parser("stats", help="Database statistics")

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
