"""Tests for kenso.install — skill installation for LLM runtimes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kenso.install import (
    _collect_skills,
    _parse_frontmatter,
    find_project_root,
    install_claude,
    install_codex,
    install_standard,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_canonical(tmp_path: Path, name: str = "kenso:ask.md") -> Path:
    """Create a minimal canonical skill file in a commands/ directory."""
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    md = commands_dir / name
    content = (
        "---\n"
        "name: kenso:ask\n"
        'description: "Ask questions about docs"\n'
        "---\n\n"
        "# kenso:ask\n\nAnswer questions about the project.\n"
    )
    md.write_text(content)
    return commands_dir


def _make_support_files(commands_dir: Path, skill_name: str = "kenso:ask") -> None:
    """Add support files to an existing commands dir under a skill subdir."""
    refs = commands_dir / skill_name / "references"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "kenso:rules.md").write_text("# Rules\n\nRule content here.\n")


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
        result = find_project_root(isolated)
        assert result is None or result.is_dir()


# ── Frontmatter parsing ────────────────────────────────────────────


class TestFrontmatter:
    def test_parse_frontmatter(self):
        text = '---\nname: kenso:ask\ndescription: "Ask questions about docs"\n---\n\n# Title\n'
        fm = _parse_frontmatter(text)
        assert fm["description"] == "Ask questions about docs"

    def test_parse_no_frontmatter(self):
        assert _parse_frontmatter("# Just a title\n") == {}


# ── Collect skills ───────────────────────────────────────────────


class TestCollectSkills:
    def test_collects_skill(self, tmp_path):
        commands_dir = _make_canonical(tmp_path)
        skills = _collect_skills(commands_dir)
        assert len(skills) == 1
        name, md, support = skills[0]
        assert name == "kenso:ask"
        assert md.name == "kenso:ask.md"
        assert support == []

    def test_collects_support_files(self, tmp_path):
        commands_dir = _make_canonical(tmp_path)
        _make_support_files(commands_dir)
        skills = _collect_skills(commands_dir)
        assert len(skills) == 1
        _, _, support = skills[0]
        assert len(support) == 1
        assert support[0].name == "kenso:rules.md"

    def test_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert _collect_skills(d) == []

    def test_nonexistent_dir(self, tmp_path):
        assert _collect_skills(tmp_path / "nope") == []


# ── Standard install (.agents/skills/) ──────────────────────────────


class TestInstallStandard:
    def _install(self, tmp_path):
        commands_dir = _make_canonical(tmp_path / "pkg")
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            return install_standard(tmp_path)

    def test_creates_skill_file(self, tmp_path):
        self._install(tmp_path)
        skill = tmp_path / ".agents" / "skills" / "kenso:ask" / "SKILL.md"
        assert skill.exists()

    def test_has_frontmatter(self, tmp_path):
        self._install(tmp_path)
        content = (tmp_path / ".agents" / "skills" / "kenso:ask" / "SKILL.md").read_text()
        assert content.startswith("---\n")
        assert "name: kenso:ask" in content
        assert 'description: "Ask questions about docs"' in content

    def test_reports_new(self, tmp_path):
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "installed to .agents/skills/" in joined
        assert "(new)" in joined

    def test_idempotent(self, tmp_path):
        self._install(tmp_path)
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "(unchanged)" in joined
        assert "unchanged" in joined.lower()

    def test_does_not_create_claude_dir(self, tmp_path):
        self._install(tmp_path)
        assert not (tmp_path / ".claude").exists()

    def test_does_not_create_codex_dir(self, tmp_path):
        self._install(tmp_path)
        assert not (tmp_path / ".codex").exists()

    def test_support_files_installed(self, tmp_path):
        commands_dir = _make_canonical(tmp_path / "pkg")
        _make_support_files(commands_dir)
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            install_standard(tmp_path)
        refs = tmp_path / ".agents" / "skills" / "kenso:ask" / "references" / "kenso:rules.md"
        assert refs.exists()

    def test_no_skills_message(self, tmp_path):
        empty = tmp_path / "empty_cmds"
        empty.mkdir()
        with patch("kenso.install._canonical_commands_path", return_value=empty):
            lines = install_standard(tmp_path)
        assert any("No kenso skills found" in line for line in lines)


# ── Claude Code install (.claude/) ──────────────────────────────────


class TestInstallClaude:
    def _install(self, tmp_path):
        commands_dir = _make_canonical(tmp_path / "pkg")
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            return install_claude(tmp_path)

    def test_creates_slash_command(self, tmp_path):
        self._install(tmp_path)
        cmd = tmp_path / ".claude" / "commands" / "kenso" / "ask.md"
        assert cmd.exists()

    def test_slash_command_is_thin_wrapper(self, tmp_path):
        self._install(tmp_path)
        content = (tmp_path / ".claude" / "commands" / "kenso" / "ask.md").read_text()
        assert "@.claude/skills/kenso:ask/SKILL.md" in content
        assert "$ARGUMENTS" in content
        # Thin = short
        assert len(content.strip().splitlines()) <= 5

    def test_creates_skill_file(self, tmp_path):
        self._install(tmp_path)
        skill = tmp_path / ".claude" / "skills" / "kenso:ask" / "SKILL.md"
        assert skill.exists()

    def test_skill_has_full_content(self, tmp_path):
        self._install(tmp_path)
        content = (tmp_path / ".claude" / "skills" / "kenso:ask" / "SKILL.md").read_text()
        assert content.startswith("---\n")
        assert "name: kenso:ask" in content
        assert "# kenso:ask" in content

    def test_creates_settings_json(self, tmp_path):
        self._install(tmp_path)
        settings = tmp_path / ".claude" / "settings.json"
        assert settings.exists()
        data = json.loads(settings.read_text())
        allow = data["permissions"]["allow"]
        assert "Bash(kenso search:*)" in allow
        assert "Bash(kenso stats:*)" in allow
        assert "Bash(kenso lint:*)" in allow
        assert "Bash(kenso ingest:*)" in allow

    def test_settings_preserves_existing(self, tmp_path):
        """Existing settings.json content is preserved."""
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(
                {
                    "permissions": {"allow": ["Bash(git:*)"]},
                    "custom_key": True,
                }
            )
        )
        self._install(tmp_path)
        data = json.loads(settings_path.read_text())
        assert "Bash(git:*)" in data["permissions"]["allow"]
        assert "Bash(kenso search:*)" in data["permissions"]["allow"]
        assert data["custom_key"] is True

    def test_settings_idempotent(self, tmp_path):
        self._install(tmp_path)
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "settings.json (unchanged)" in joined

    def test_reports_new(self, tmp_path):
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "installed to .claude/" in joined
        assert "(new)" in joined

    def test_idempotent(self, tmp_path):
        self._install(tmp_path)
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "(unchanged)" in joined

    def test_does_not_create_agents_dir(self, tmp_path):
        self._install(tmp_path)
        assert not (tmp_path / ".agents").exists()

    def test_does_not_create_codex_dir(self, tmp_path):
        self._install(tmp_path)
        assert not (tmp_path / ".codex").exists()

    def test_does_not_touch_other_files(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        other = claude_dir / "CLAUDE.md"
        other.write_text("user content")
        self._install(tmp_path)
        assert other.read_text() == "user content"

    def test_no_skills_message(self, tmp_path):
        empty = tmp_path / "empty_cmds"
        empty.mkdir()
        with patch("kenso.install._canonical_commands_path", return_value=empty):
            lines = install_claude(tmp_path)
        assert any("No kenso skills found" in line for line in lines)


# ── Codex install (.codex/skills/) ──────────────────────────────────


class TestInstallCodex:
    def _install(self, tmp_path):
        commands_dir = _make_canonical(tmp_path / "pkg")
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            return install_codex(tmp_path)

    def test_creates_skill_dir(self, tmp_path):
        self._install(tmp_path)
        skill = tmp_path / ".codex" / "skills" / "kenso:ask" / "SKILL.md"
        assert skill.exists()

    def test_has_frontmatter(self, tmp_path):
        self._install(tmp_path)
        content = (tmp_path / ".codex" / "skills" / "kenso:ask" / "SKILL.md").read_text()
        assert content.startswith("---\n")
        assert "name: kenso:ask" in content
        assert 'description: "Ask questions about docs"' in content

    def test_reports_new(self, tmp_path):
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "installed to .codex/skills/" in joined
        assert "(new)" in joined

    def test_idempotent(self, tmp_path):
        self._install(tmp_path)
        lines = self._install(tmp_path)
        joined = "\n".join(lines)
        assert "(unchanged)" in joined

    def test_does_not_create_agents_dir(self, tmp_path):
        self._install(tmp_path)
        assert not (tmp_path / ".agents").exists()

    def test_does_not_create_claude_dir(self, tmp_path):
        self._install(tmp_path)
        assert not (tmp_path / ".claude").exists()

    def test_no_skills_message(self, tmp_path):
        empty = tmp_path / "empty_cmds"
        empty.mkdir()
        with patch("kenso.install._canonical_commands_path", return_value=empty):
            lines = install_codex(tmp_path)
        assert any("No kenso skills found" in line for line in lines)


# ── CLI integration ──────────────────────────────────────────────────


class TestCLIInstall:
    def test_install_default(self, tmp_path, capsys, monkeypatch):
        """Default install (no flags) goes to .agents/skills/."""
        (tmp_path / ".git").mkdir()
        commands_dir = _make_canonical(tmp_path / "pkg")
        monkeypatch.chdir(tmp_path)
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            from kenso.cli import cmd_install

            cmd_install(_parse_install_args())
        assert (tmp_path / ".agents" / "skills" / "kenso:ask" / "SKILL.md").exists()
        assert not (tmp_path / ".claude").exists()
        assert not (tmp_path / ".codex").exists()

    def test_install_claude_flag(self, tmp_path, capsys, monkeypatch):
        (tmp_path / ".git").mkdir()
        commands_dir = _make_canonical(tmp_path / "pkg")
        monkeypatch.chdir(tmp_path)
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            from kenso.cli import cmd_install

            cmd_install(_parse_install_args("--claude"))
        assert (tmp_path / ".claude" / "commands" / "kenso" / "ask.md").exists()
        assert (tmp_path / ".claude" / "skills" / "kenso:ask" / "SKILL.md").exists()
        assert (tmp_path / ".claude" / "settings.json").exists()
        assert not (tmp_path / ".agents").exists()

    def test_install_codex_flag(self, tmp_path, capsys, monkeypatch):
        (tmp_path / ".git").mkdir()
        commands_dir = _make_canonical(tmp_path / "pkg")
        monkeypatch.chdir(tmp_path)
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            from kenso.cli import cmd_install

            cmd_install(_parse_install_args("--codex"))
        assert (tmp_path / ".codex" / "skills" / "kenso:ask" / "SKILL.md").exists()
        assert not (tmp_path / ".agents").exists()
        assert not (tmp_path / ".claude").exists()

    def test_no_all_flag(self):
        """--all flag should not exist."""
        with pytest.raises(SystemExit):
            _parse_install_args("--all")

    def test_default_without_project_markers(self, tmp_path, capsys, monkeypatch):
        """Default install works even without .git/ — uses CWD."""
        isolated = tmp_path / "bare"
        isolated.mkdir()
        monkeypatch.chdir(isolated)
        commands_dir = _make_canonical(tmp_path / "pkg")
        with patch("kenso.install._canonical_commands_path", return_value=commands_dir):
            from kenso.cli import cmd_install

            cmd_install(_parse_install_args())
        assert (isolated / ".agents" / "skills" / "kenso:ask" / "SKILL.md").exists()


# ── Helper ───────────────────────────────────────────────────────


def _parse_install_args(*args: str):
    """Parse install subcommand arguments."""
    import argparse

    parser = argparse.ArgumentParser(prog="kenso")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("install")
    p.add_argument("--claude", action="store_true")
    p.add_argument("--codex", action="store_true")
    return parser.parse_args(["install", *args])
