"""CLI: serve, ingest, search, stats, lint."""

from __future__ import annotations

import argparse
import asyncio
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

    asyncio.run(_run())


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
    }[args.command](args)
