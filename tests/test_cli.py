"""Tests for kenso.cli — argument parsing, subcommands, output."""

from __future__ import annotations

import json

import pytest

from kenso.cli import cmd_ingest, cmd_search, cmd_stats, main


@pytest.fixture(autouse=True)
def _use_memory_db(monkeypatch):
    """Use in-memory SQLite for all CLI tests."""
    monkeypatch.setenv("KENSO_DATABASE_URL", ":memory:")


class TestCLINoArgs:
    def test_no_command_exits(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["kenso"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code in (1, 2)  # 1 from our code, 2 from argparse


class TestCLIMain:
    def test_version(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["kenso", "--version"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0


class TestCLIIngest:
    def test_ingest_nonexistent_path(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["kenso", "ingest", "/nonexistent/path/xyz"])
        cmd_ingest(_parse_args("ingest", "/nonexistent/path/xyz"))
        captured = capsys.readouterr()
        assert "0 ingested" in captured.out or "error" in captured.out.lower()

    def test_ingest_shows_lint_summary(self, tmp_path, capsys):
        md = tmp_path / "doc.md"
        md.write_text(
            "---\ntags: [a]\n---\n# My Title\n\nSome preamble text here.\n\n"
            "## Section One\n\nContent of section one with enough text.\n"
        )
        cmd_ingest(_parse_args("ingest", str(tmp_path)))
        captured = capsys.readouterr()
        assert "1 ingested" in captured.out
        assert "Quality score:" in captured.out

    def test_ingest_lint_matches_standalone(self, tmp_path, capsys):
        md = tmp_path / "doc.md"
        md.write_text(
            "---\ntags: [a]\n---\n# My Title\n\nSome preamble text here.\n\n"
            "## Section One\n\nContent of section one with enough text.\n"
        )
        cmd_ingest(_parse_args("ingest", str(tmp_path)))
        captured = capsys.readouterr()

        from kenso.lint import lint_path

        lint_result = lint_path(str(tmp_path))
        assert f"Quality score: {lint_result.score}/100" in captured.out

    def test_ingest_empty_dir_no_lint(self, tmp_path, capsys):
        cmd_ingest(_parse_args("ingest", str(tmp_path)))
        captured = capsys.readouterr()
        assert "0 ingested" in captured.out
        assert "Quality score:" not in captured.out

    def test_ingest_lint_failure_does_not_fail_ingest(self, tmp_path, monkeypatch, capsys):
        md = tmp_path / "doc.md"
        md.write_text(
            "---\ntags: [a]\n---\n# My Title\n\nSome preamble text here.\n\n"
            "## Section One\n\nContent of section one with enough text.\n"
        )
        monkeypatch.setattr(
            "kenso.lint.lint_path",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        cmd_ingest(_parse_args("ingest", str(tmp_path)))
        captured = capsys.readouterr()
        assert "1 ingested" in captured.out
        assert "Could not generate quality summary" in captured.out


class TestCLIIngestJSON:
    def test_json_output_is_valid(self, tmp_path, capsys):
        md = tmp_path / "doc.md"
        md.write_text(
            "---\ntags: [a]\ncategory: docs\n---\n# My Title\n\nSome preamble text.\n\n"
            "## Section One\n\nContent of section one with enough text.\n"
        )
        cmd_ingest(_parse_args("ingest", str(tmp_path), "--json"))
        captured = capsys.readouterr()
        import json

        data = json.loads(captured.out)
        assert "ingest" in data
        assert "lint" in data

    def test_json_ingest_fields(self, tmp_path, capsys):
        md = tmp_path / "doc.md"
        md.write_text(
            "---\ntags: [a]\ncategory: docs\n---\n# My Title\n\nSome preamble text.\n\n"
            "## Section One\n\nContent of section one with enough text.\n"
        )
        cmd_ingest(_parse_args("ingest", str(tmp_path), "--json"))
        captured = capsys.readouterr()
        import json

        ingest = json.loads(captured.out)["ingest"]
        assert ingest["path"] == str(tmp_path)
        assert ingest["total_files"] == 1
        assert ingest["ingested"] == 1
        assert ingest["unchanged"] == 0
        assert ingest["skipped"] == 0
        assert ingest["total_chunks"] > 0
        assert len(ingest["files"]) == 1
        f = ingest["files"][0]
        assert f["status"] == "ingested"
        assert f["title"] == "My Title"
        assert f["category"] == "docs"
        assert f["chunks"] > 0

    def test_json_lint_matches_standalone(self, tmp_path, capsys):
        md = tmp_path / "doc.md"
        md.write_text(
            "---\ntags: [a]\n---\n# My Title\n\nSome preamble text here.\n\n"
            "## Section One\n\nContent of section one with enough text.\n"
        )
        cmd_ingest(_parse_args("ingest", str(tmp_path), "--json"))
        captured = capsys.readouterr()
        import json

        lint_from_ingest = json.loads(captured.out)["lint"]

        from kenso.lint import format_json as lint_format_json
        from kenso.lint import lint_path

        lint_result = lint_path(str(tmp_path))
        lint_standalone = json.loads(lint_format_json(lint_result))

        assert lint_from_ingest == lint_standalone

    def test_json_empty_dir(self, tmp_path, capsys):
        cmd_ingest(_parse_args("ingest", str(tmp_path), "--json"))
        captured = capsys.readouterr()
        import json

        data = json.loads(captured.out)
        assert data["ingest"]["total_files"] == 1  # skipped entry
        assert data["ingest"]["ingested"] == 0
        assert "lint" not in data

    def test_json_no_extra_stdout(self, tmp_path, capsys):
        md = tmp_path / "doc.md"
        md.write_text(
            "---\ntags: [a]\n---\n# My Title\n\nSome preamble text here.\n\n"
            "## Section One\n\nContent of section one with enough text.\n"
        )
        cmd_ingest(_parse_args("ingest", str(tmp_path), "--json"))
        captured = capsys.readouterr()
        import json

        # stdout must be pure parseable JSON — no banners, no warnings
        json.loads(captured.out)  # raises if not valid JSON


class TestCLIStats:
    def test_stats_human(self, capsys):
        cmd_stats(_parse_args("stats"))
        captured = capsys.readouterr()
        assert "kenso" in captured.out and "stats" in captured.out


class TestCLISearch:
    """Tests for `kenso search` with --json, --limit, --category flags."""

    @pytest.fixture()
    def _ingested_docs(self, tmp_path, monkeypatch):
        """Ingest a small doc set so search has something to find."""
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("KENSO_DATABASE_URL", db_path)

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "settlement.md").write_text(
            "---\ntitle: Settlement Lifecycle\ncategory: post-trade\n"
            "tags: [settlement, clearing]\n---\n# Settlement Lifecycle\n\n"
            "## Failed Settlement Handling\n\n"
            "When a settlement fails due to insufficient securities, the "
            "clearing house initiates a buy-in procedure.\n"
        )
        (docs / "reporting.md").write_text(
            "---\ntitle: CNMV Reporting\ncategory: regulatory\n"
            "tags: [reporting, cnmv]\n---\n# CNMV Reporting\n\n"
            "## Settlement Reports\n\n"
            "Settlement data must be reported to CNMV within T+1.\n"
        )
        (docs / "onboarding.md").write_text(
            "---\ntitle: Client Onboarding\ncategory: operations\n"
            "tags: [kyc, onboarding]\n---\n# Client Onboarding\n\n"
            "## KYC Process\n\nNew clients must complete KYC verification.\n"
        )
        cmd_ingest(_parse_args("ingest", str(docs)))

    def test_default_no_flags(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement"))
        out = capsys.readouterr().out
        # Human-readable output — should not be JSON
        assert "results for" in out  # header
        assert '"query"' not in out

    def test_json_output_valid(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement", "--json"))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["query"] == "settlement"
        assert isinstance(data["total_results"], int)
        assert isinstance(data["results"], list)

    def test_json_schema_fields(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement", "--json"))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["total_results"] > 0
        r = data["results"][0]
        for key in (
            "score",
            "path",
            "title",
            "category",
            "tags",
            "preview",
            "snippet",
            "related_count",
            "cascade_stage",
            "relevance",
        ):
            assert key in r, f"Missing key: {key}"

    def test_cascade_stage_values(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement", "--json"))
        out = capsys.readouterr().out
        data = json.loads(out)
        for r in data["results"]:
            assert r["cascade_stage"] in ("AND", "NEAR", "OR", None)

    def test_relevance_values(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement", "--json"))
        out = capsys.readouterr().out
        data = json.loads(out)
        for r in data["results"]:
            assert r["relevance"] in ("high", "medium", "low")

    def test_limit(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement", "--json", "--limit", "1"))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["total_results"] <= 1

    def test_category_filter(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement", "--json", "--category", "post-trade"))
        out = capsys.readouterr().out
        data = json.loads(out)
        for r in data["results"]:
            assert r["category"] == "post-trade"

    def test_category_no_match_returns_empty(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement", "--json", "--category", "nonexistent"))
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["total_results"] == 0
        assert data["results"] == []

    def test_all_flags_combined(self, _ingested_docs, capsys):
        cmd_search(
            _parse_args(
                "search", "settlement", "--json", "--limit", "1", "--category", "post-trade"
            )
        )
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["total_results"] <= 1
        for r in data["results"]:
            assert r["category"] == "post-trade"

    def test_json_no_extra_stdout(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement", "--json"))
        out = capsys.readouterr().out
        # stdout must be pure parseable JSON
        json.loads(out)

    def test_human_output_shows_cascade_stage(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement"))
        out = capsys.readouterr().out
        # Human-readable output should include AND, NEAR, or OR labels
        assert any(stage in out for stage in ("AND", "NEAR", "OR")), (
            f"Expected cascade stage label in output: {out}"
        )

    def test_limit_in_human_mode(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement", "--limit", "1"))
        out = capsys.readouterr().out
        # Count result blocks — each has a score (digits followed by dot)
        import re

        score_lines = [line for line in out.splitlines() if re.match(r"^\d+\.\d+\s", line.strip())]
        assert len(score_lines) <= 1

    def test_category_in_human_mode(self, _ingested_docs, capsys):
        cmd_search(_parse_args("search", "settlement", "--category", "post-trade"))
        out = capsys.readouterr().out
        assert "settlement" in out.lower()


# ── Helper ───────────────────────────────────────────────────────────


def _parse_args(*args: str):
    """Parse CLI arguments without running main()."""
    import argparse

    parser = argparse.ArgumentParser(prog="kenso")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("ingest")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.add_argument("--db", type=str, default=None)

    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--category", type=str, default=None)
    p.add_argument("--db", type=str, default=None)

    p = sub.add_parser("stats")
    p.add_argument("--db", type=str, default=None)

    return parser.parse_args(list(args))


class TestCLIDbFlag:
    """Tests for --db flag across commands."""

    def test_ingest_creates_db_at_flag_path(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("KENSO_DATABASE_URL", raising=False)
        db_path = str(tmp_path / "custom.db")
        md = tmp_path / "doc.md"
        md.write_text("# Hello\n\nSome content here.\n")
        cmd_ingest(_parse_args("ingest", str(tmp_path), "--db", db_path))
        assert (tmp_path / "custom.db").is_file()

    def test_search_uses_db_flag(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("KENSO_DATABASE_URL", raising=False)
        db_path = str(tmp_path / "custom.db")
        md = tmp_path / "docs" / "doc.md"
        md.parent.mkdir()
        md.write_text(
            "---\ntags: [test]\n---\n# Hello World\n\n"
            "## Overview\n\nThis document contains enough content to be ingested "
            "properly by the kenso system for search testing purposes.\n"
        )
        # Ingest first, then search using same --db path
        cmd_ingest(_parse_args("ingest", str(md.parent), "--db", db_path))
        cmd_search(_parse_args("search", "hello", "--db", db_path))
        out = capsys.readouterr().out
        assert "No results" not in out

    def test_stats_uses_db_flag(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("KENSO_DATABASE_URL", raising=False)
        db_path = str(tmp_path / "custom.db")
        md = tmp_path / "doc.md"
        md.write_text("# Hello\n\nSome content here.\n")
        cmd_ingest(_parse_args("ingest", str(tmp_path), "--db", db_path))
        cmd_stats(_parse_args("stats", "--db", db_path))
        out = capsys.readouterr().out
        assert "Documents:" in out

    def test_db_flag_overrides_env_var(self, tmp_path, monkeypatch, capsys):
        env_db = str(tmp_path / "env.db")
        flag_db = str(tmp_path / "flag.db")
        monkeypatch.setenv("KENSO_DATABASE_URL", env_db)
        md = tmp_path / "doc.md"
        md.write_text("# Hello\n\nSome content here.\n")
        cmd_ingest(_parse_args("ingest", str(tmp_path), "--db", flag_db))
        assert (tmp_path / "flag.db").is_file()
        assert not (tmp_path / "env.db").exists()

    def test_search_nonexistent_db_fails(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("KENSO_DATABASE_URL", raising=False)
        db_path = str(tmp_path / "nonexistent.db")
        with pytest.raises(SystemExit) as exc_info:
            cmd_search(_parse_args("search", "anything", "--db", db_path))
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "Database not found" in out
        assert "kenso ingest" in out

    def test_stats_nonexistent_db_fails(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("KENSO_DATABASE_URL", raising=False)
        db_path = str(tmp_path / "nonexistent.db")
        with pytest.raises(SystemExit) as exc_info:
            cmd_stats(_parse_args("stats", "--db", db_path))
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "Database not found" in out

    def test_without_db_flag_cascade_still_works(self, tmp_path, monkeypatch, capsys):
        """Backward compat: without --db, env var cascade still works."""
        db_path = str(tmp_path / "env.db")
        monkeypatch.setenv("KENSO_DATABASE_URL", db_path)
        md = tmp_path / "doc.md"
        md.write_text("# Hello\n\nSome content here.\n")
        cmd_ingest(_parse_args("ingest", str(tmp_path)))
        assert (tmp_path / "env.db").is_file()
