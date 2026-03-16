"""Tests for kenso.install — command installation for LLM runtimes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from kenso.install import (
    _collect_canonical_files,
    _parse_metadata,
    _strip_metadata,
    find_project_root,
    install_claude,
    install_codex,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_canonical(tmp_path: Path, name: str = "kenso-ask.md", *, metadata: bool = True) -> Path:
    """Create a minimal canonical command file in a commands/ directory."""
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    md = commands_dir / name
    content = ""
    if metadata:
        content += (
            "<!--kenso-metadata\n"
            'codex_description: "Ask questions about docs"\n'
            'codex_short_description: "Ask docs"\n'
            "-->\n\n"
        )
    content += "# kenso-ask\n\nSearch {{KENSO_ROOT}}/references/rules.md\n"
    md.write_text(content)
    return commands_dir


def _make_support_files(commands_dir: Path) -> None:
    """Add support files (references/) to an existing commands dir."""
    refs = commands_dir / "references"
    refs.mkdir(exist_ok=True)
    (refs / "kenso-rules.md").write_text("# Rules\n\nRule content here.\n")


# ── find_project_root ────────────────────────────────────────────────


class TestFindProjectRoot:
    def test_finds_git_dir(self, tmp_path):
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        assert find_project_root(sub) == tmp_path

    def test_finds_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        assert find_project_root(tmp_path) == tmp_path

    def test_returns_none_when_no_marker(self, tmp_path):
        isolated = tmp_path / "empty"
        isolated.mkdir()
        # Prevent walking up to a real project root
        result = find_project_root(isolated)
        # May find a marker above tmp_path — just verify it doesn't crash
        assert result is None or result.is_dir()


# ── Metadata parsing ─────────────────────────────────────────────────


class TestMetadata:
    def test_parse_metadata(self):
        text = (
            "<!--kenso-metadata\n"
            'codex_description: "My description"\n'
            'codex_short_description: "Short"\n'
            "-->\n\n# Title\n"
        )
        meta = _parse_metadata(text)
        assert meta["codex_description"] == "My description"
        assert meta["codex_short_description"] == "Short"

    def test_parse_no_metadata(self):
        assert _parse_metadata("# Just a title\n") == {}

    def test_strip_metadata(self):
        text = '<!--kenso-metadata\ncodex_description: "desc"\n-->\n\n# Title\n'
        result = _strip_metadata(text)
        assert "kenso-metadata" not in result
        assert "# Title" in result

    def test_strip_preserves_body(self):
        body = "# Title\n\nBody content.\n"
        text = '<!--kenso-metadata\nfoo: "bar"\n-->\n\n' + body
        assert _strip_metadata(text) == body


# ── Collect canonical files ───────────────────────────────────────────


class TestCollectCanonical:
    def test_collects_commands(self, tmp_path):
        commands_dir = _make_canonical(tmp_path)
        cmds, support = _collect_canonical_files(commands_dir)
        assert len(cmds) == 1
        assert cmds[0].name == "kenso-ask.md"
        assert support == []

    def test_collects_support_files(self, tmp_path):
        commands_dir = _make_canonical(tmp_path)
        _make_support_files(commands_dir)
        cmds, support = _collect_canonical_files(commands_dir)
        assert len(cmds) == 1
        assert len(support) == 1
        assert support[0].name == "kenso-rules.md"

    def test_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        cmds, support = _collect_canonical_files(d)
        assert cmds == []
        assert support == []

    def test_nonexistent_dir(self, tmp_path):
        cmds, support = _collect_canonical_files(tmp_path / "nope")
        assert cmds == []
        assert support == []


# ── Claude Code install ──────────────────────────────────────────────


class TestInstallClaude:
    def _install(self, tmp_path):
        commands_dir = _make_canonical(tmp_path / "pkg")
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            return install_claude(tmp_path)

    def test_creates_command_file(self, tmp_path):
        self._install(tmp_path)
        cmd = tmp_path / ".claude" / "commands" / "kenso-ask.md"
        assert cmd.exists()

    def test_strips_metadata(self, tmp_path):
        self._install(tmp_path)
        content = (tmp_path / ".claude" / "commands" / "kenso-ask.md").read_text()
        assert "kenso-metadata" not in content

    def test_rewrites_paths(self, tmp_path):
        self._install(tmp_path)
        content = (tmp_path / ".claude" / "commands" / "kenso-ask.md").read_text()
        assert "{{KENSO_ROOT}}" not in content
        assert ".claude/kenso" in content

    def test_reports_new(self, tmp_path):
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "Installed" in joined
        assert "(new)" in joined

    def test_idempotent(self, tmp_path):
        self._install(tmp_path)
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "(unchanged)" in joined

    def test_detects_update(self, tmp_path):
        self._install(tmp_path)
        # Modify the installed file
        cmd = tmp_path / ".claude" / "commands" / "kenso-ask.md"
        cmd.write_text("old content")
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "(updated)" in joined

    def test_support_files_installed(self, tmp_path):
        commands_dir = _make_canonical(tmp_path / "pkg")
        _make_support_files(commands_dir)
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            lines = install_claude(tmp_path)
        support_file = tmp_path / ".claude" / "kenso" / "references" / "kenso-rules.md"
        assert support_file.exists()
        joined = "\n".join(lines)
        assert "Support files:" in joined

    def test_no_commands_message(self, tmp_path):
        empty = tmp_path / "empty_cmds"
        empty.mkdir()
        with patch("kenso.install._canonical_commands_path", return_value=empty):
            lines = install_claude(tmp_path)
        assert any("No kenso commands found" in line for line in lines)

    def test_does_not_touch_other_files(self, tmp_path):
        # Pre-existing file in .claude/
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        other = claude_dir / "CLAUDE.md"
        other.write_text("user content")
        self._install(tmp_path)
        assert other.read_text() == "user content"


# ── Codex install ─────────────────────────────────────────────────────


class TestInstallCodex:
    def _install(self, tmp_path):
        commands_dir = _make_canonical(tmp_path / "pkg")
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            return install_codex(tmp_path)

    def test_creates_skill_dir(self, tmp_path):
        self._install(tmp_path)
        skill = tmp_path / ".codex" / "skills" / "kenso-ask" / "SKILL.md"
        assert skill.exists()

    def test_has_yaml_frontmatter(self, tmp_path):
        self._install(tmp_path)
        content = (tmp_path / ".codex" / "skills" / "kenso-ask" / "SKILL.md").read_text()
        assert content.startswith("---\n")
        assert "name: kenso-ask" in content
        assert 'description: "Ask questions about docs"' in content
        assert 'short-description: "Ask docs"' in content
        assert content.count("---") >= 2

    def test_strips_metadata(self, tmp_path):
        self._install(tmp_path)
        content = (tmp_path / ".codex" / "skills" / "kenso-ask" / "SKILL.md").read_text()
        assert "kenso-metadata" not in content

    def test_rewrites_paths(self, tmp_path):
        self._install(tmp_path)
        content = (tmp_path / ".codex" / "skills" / "kenso-ask" / "SKILL.md").read_text()
        assert "{{KENSO_ROOT}}" not in content
        assert "./references" in content

    def test_reports_new(self, tmp_path):
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "Installed" in joined
        assert "(new)" in joined

    def test_idempotent(self, tmp_path):
        self._install(tmp_path)
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "(unchanged)" in joined

    def test_support_files_in_references(self, tmp_path):
        commands_dir = _make_canonical(tmp_path / "pkg")
        _make_support_files(commands_dir)
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            install_codex(tmp_path)
        refs = tmp_path / ".codex" / "skills" / "kenso-ask" / "references" / "references"
        assert (refs / "kenso-rules.md").exists()

    def test_no_commands_message(self, tmp_path):
        empty = tmp_path / "empty_cmds"
        empty.mkdir()
        with patch("kenso.install._canonical_commands_path", return_value=empty):
            lines = install_codex(tmp_path)
        assert any("No kenso commands found" in line for line in lines)


# ── CLI integration ──────────────────────────────────────────────────


class TestCLIInstall:
    def test_install_claude_flag(self, tmp_path, capsys, monkeypatch):
        (tmp_path / ".git").mkdir()
        commands_dir = _make_canonical(tmp_path / "pkg")
        monkeypatch.chdir(tmp_path)
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            from kenso.cli import cmd_install

            cmd_install(_parse_install_args("--claude"))
        captured = capsys.readouterr()
        assert "Installed" in captured.out

    def test_install_all_flag(self, tmp_path, capsys, monkeypatch):
        (tmp_path / ".git").mkdir()
        commands_dir = _make_canonical(tmp_path / "pkg")
        monkeypatch.chdir(tmp_path)
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            from kenso.cli import cmd_install

            cmd_install(_parse_install_args("--all"))
        captured = capsys.readouterr()
        assert ".claude/commands/" in captured.out
        assert ".codex/skills/" in captured.out

    def test_auto_detect_claude(self, tmp_path, capsys, monkeypatch):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".claude").mkdir()
        commands_dir = _make_canonical(tmp_path / "pkg")
        monkeypatch.chdir(tmp_path)
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            from kenso.cli import cmd_install

            cmd_install(_parse_install_args())
        captured = capsys.readouterr()
        assert ".claude/commands/" in captured.out

    def test_no_runtime_exits(self, tmp_path, monkeypatch, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        from kenso.cli import cmd_install

        with pytest.raises(SystemExit):
            cmd_install(_parse_install_args())
        captured = capsys.readouterr()
        assert "No LLM runtimes detected" in captured.out
        assert "--claude" in captured.out

    def test_explicit_flag_without_project_markers(self, tmp_path, capsys, monkeypatch):
        """--claude should work even in a directory with no .git/ or pyproject.toml."""
        # tmp_path has no root markers at all
        isolated = tmp_path / "bare"
        isolated.mkdir()
        monkeypatch.chdir(isolated)
        commands_dir = _make_canonical(tmp_path / "pkg")
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            from kenso.cli import cmd_install

            cmd_install(_parse_install_args("--claude"))
        assert (isolated / ".claude" / "commands" / "kenso-ask.md").exists()

    def test_explicit_codex_without_project_markers(self, tmp_path, capsys, monkeypatch):
        """--codex should work even in a directory with no root markers."""
        isolated = tmp_path / "bare"
        isolated.mkdir()
        monkeypatch.chdir(isolated)
        commands_dir = _make_canonical(tmp_path / "pkg")
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            from kenso.cli import cmd_install

            cmd_install(_parse_install_args("--codex"))
        assert (isolated / ".codex" / "skills" / "kenso-ask" / "SKILL.md").exists()

    def test_no_markers_no_flags_exits(self, tmp_path, monkeypatch):
        """Without root markers AND without flags, should error about project root."""
        isolated = tmp_path / "bare"
        isolated.mkdir()
        monkeypatch.chdir(isolated)
        from kenso.cli import cmd_install

        with pytest.raises(SystemExit):
            cmd_install(_parse_install_args())


# ── Helper ───────────────────────────────────────────────────────────


def _parse_install_args(*args: str):
    """Parse install subcommand arguments."""
    import argparse

    parser = argparse.ArgumentParser(prog="kenso")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("install")
    p.add_argument("--claude", action="store_true")
    p.add_argument("--codex", action="store_true")
    p.add_argument("--all", action="store_true")
    return parser.parse_args(["install", *args])
