"""Install kenso commands into LLM runtime directories."""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

__all__ = ["install_claude", "install_codex", "find_project_root"]

# Markers for detecting project root
_ROOT_MARKERS = (".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml")

_METADATA_RE = re.compile(r"<!--kenso-metadata\s*\n(.*?)-->\s*\n?", re.DOTALL)
_METADATA_FIELD_RE = re.compile(r"^(\w+):\s*\"(.+?)\"$", re.MULTILINE)


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from *start* looking for a project-root marker."""
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        if any((directory / m).exists() for m in _ROOT_MARKERS):
            return directory
    return None


def _canonical_commands_path() -> Path:
    """Return the path to the canonical commands directory inside the package."""
    return Path(str(files("kenso") / "commands"))


def _parse_metadata(text: str) -> dict[str, str]:
    """Extract metadata fields from the ``<!--kenso-metadata ... -->`` block."""
    match = _METADATA_RE.search(text)
    if not match:
        return {}
    block = match.group(1)
    return dict(_METADATA_FIELD_RE.findall(block))


def _strip_metadata(text: str) -> str:
    """Remove the ``<!--kenso-metadata ... -->`` block from *text*."""
    return _METADATA_RE.sub("", text, count=1)


def _collect_canonical_files(
    commands_dir: Path,
) -> tuple[list[Path], list[Path]]:
    """Return (command_files, support_files) found under *commands_dir*.

    Command files are ``*.md`` directly inside *commands_dir*.
    Support files are everything inside subdirectories (workflows/, agents/,
    references/, templates/).
    """
    if not commands_dir.is_dir():
        return [], []

    command_files = sorted(commands_dir.glob("*.md"))
    support_files: list[Path] = []
    for child in sorted(commands_dir.iterdir()):
        if child.is_dir():
            support_files.extend(sorted(child.rglob("*")))
    # Only keep actual files, not directories
    support_files = [f for f in support_files if f.is_file()]
    return command_files, support_files


# ── Claude Code ──────────────────────────────────────────────────────


def install_claude(root: Path) -> list[str]:
    """Install kenso commands for Claude Code.

    Returns a list of human-readable status lines.
    """
    commands_dir = _canonical_commands_path()
    command_files, support_files = _collect_canonical_files(commands_dir)

    if not command_files and not support_files:
        return [
            "No kenso commands found in package. This is expected if you're "
            "running a development version."
        ]

    target_commands = root / ".claude" / "commands"
    target_support = root / ".claude" / "kenso"
    target_commands.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    cmd_statuses: list[str] = []

    for src in command_files:
        dest = target_commands / src.name
        raw = src.read_text(encoding="utf-8")
        converted = _strip_metadata(raw)
        converted = converted.replace("{{KENSO_ROOT}}", ".claude/kenso")

        status = _write_status(dest, converted)
        cmd_statuses.append(f"  {src.name} ({status})")

    new_count = sum(1 for s in cmd_statuses if "new" in s)
    updated_count = sum(1 for s in cmd_statuses if "updated" in s)
    unchanged_count = sum(1 for s in cmd_statuses if "unchanged" in s)

    verb = _summary_verb(new_count, updated_count, unchanged_count)
    total_changed = new_count + updated_count
    if total_changed:
        lines.append(
            f"{verb} {total_changed} command{'s' if total_changed != 1 else ''}"
            f" to .claude/commands/"
        )
    else:
        lines.append("Commands in .claude/commands/ unchanged.")
    lines.extend(cmd_statuses)

    # Support files
    if support_files:
        target_support.mkdir(parents=True, exist_ok=True)
        support_statuses: list[str] = []
        for src in support_files:
            rel = src.relative_to(commands_dir)
            dest = target_support / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            raw = src.read_text(encoding="utf-8")
            converted = raw.replace("{{KENSO_ROOT}}", ".claude/kenso")
            status = _write_status(dest, converted)
            support_statuses.append(f"  {rel} ({status})")

        any_changed = any("new" in s or "updated" in s for s in support_statuses)
        if any_changed:
            lines.append("Support files: .claude/kenso/")
            lines.extend(support_statuses)
        else:
            lines.append("Support files unchanged.")
    return lines


# ── Codex CLI ────────────────────────────────────────────────────────


def install_codex(root: Path) -> list[str]:
    """Install kenso commands for Codex CLI.

    Returns a list of human-readable status lines.
    """
    commands_dir = _canonical_commands_path()
    command_files, support_files = _collect_canonical_files(commands_dir)

    if not command_files and not support_files:
        return [
            "No kenso commands found in package. This is expected if you're "
            "running a development version."
        ]

    target_skills = root / ".codex" / "skills"
    target_skills.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    cmd_statuses: list[str] = []

    for src in command_files:
        skill_name = src.stem  # e.g. "kenso-ask"
        skill_dir = target_skills / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        dest = skill_dir / "SKILL.md"

        raw = src.read_text(encoding="utf-8")
        metadata = _parse_metadata(raw)
        body = _strip_metadata(raw)
        body = body.replace("{{KENSO_ROOT}}", "./references")

        # Build SKILL.md with YAML frontmatter
        description = metadata.get("codex_description", f"Kenso {skill_name} command")
        short_desc = metadata.get("codex_short_description", skill_name)
        frontmatter = (
            "---\n"
            f"name: {skill_name}\n"
            f'description: "{description}"\n'
            "metadata:\n"
            f'  short-description: "{short_desc}"\n'
            "---\n\n"
        )
        converted = frontmatter + body

        status = _write_status(dest, converted)
        cmd_statuses.append(f"  {skill_name}/SKILL.md ({status})")

        # Copy support files into skill's references/ directory
        if support_files:
            refs_dir = skill_dir / "references"
            refs_dir.mkdir(parents=True, exist_ok=True)
            for sf in support_files:
                rel = sf.relative_to(commands_dir)
                dest_sf = refs_dir / rel
                dest_sf.parent.mkdir(parents=True, exist_ok=True)
                content = sf.read_text(encoding="utf-8")
                content = content.replace("{{KENSO_ROOT}}", "./references")
                _write_status(dest_sf, content)

    new_count = sum(1 for s in cmd_statuses if "new" in s)
    updated_count = sum(1 for s in cmd_statuses if "updated" in s)
    unchanged_count = sum(1 for s in cmd_statuses if "unchanged" in s)

    verb = _summary_verb(new_count, updated_count, unchanged_count)
    total_changed = new_count + updated_count
    if total_changed:
        lines.append(
            f"{verb} {total_changed} command{'s' if total_changed != 1 else ''} to .codex/skills/"
        )
    else:
        lines.append("Commands in .codex/skills/ unchanged.")
    lines.extend(cmd_statuses)

    return lines


# ── Helpers ──────────────────────────────────────────────────────────


def _write_status(dest: Path, content: str) -> str:
    """Write *content* to *dest*, return 'new', 'updated', or 'unchanged'."""
    if dest.exists():
        existing = dest.read_text(encoding="utf-8")
        if existing == content:
            return "unchanged"
        dest.write_text(content, encoding="utf-8")
        return "updated"
    dest.write_text(content, encoding="utf-8")
    return "new"


def _summary_verb(new: int, updated: int, unchanged: int) -> str:
    if new and not updated:
        return "Installed"
    if updated and not new:
        return "Updated"
    if new or updated:
        return "Installed/updated"
    return "Checked"
