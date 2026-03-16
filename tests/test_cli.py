"""Tests for kenso.cli — argument parsing, subcommands, output."""

from __future__ import annotations

import pytest

from kenso.cli import cmd_ingest, cmd_stats, main


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
        assert "Quality Score:" in captured.out

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
        assert f"Quality Score: {lint_result.score}/100" in captured.out

    def test_ingest_empty_dir_no_lint(self, tmp_path, capsys):
        cmd_ingest(_parse_args("ingest", str(tmp_path)))
        captured = capsys.readouterr()
        assert "0 ingested" in captured.out
        assert "Quality Score:" not in captured.out

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
        assert "Warning: Could not generate quality summary" in captured.out


class TestCLIStats:
    def test_stats_human(self, capsys):
        cmd_stats(_parse_args("stats"))
        captured = capsys.readouterr()
        assert "kenso stats" in captured.out


# ── Helper ───────────────────────────────────────────────────────────


def _parse_args(*args: str):
    """Parse CLI arguments without running main()."""
    import argparse

    parser = argparse.ArgumentParser(prog="kenso")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("ingest")
    p.add_argument("path")

    p = sub.add_parser("search")
    p.add_argument("query")

    sub.add_parser("stats")

    return parser.parse_args(list(args))
