"""Install kenso skills into LLM runtime directories."""

from __future__ import annotations

import json
import re
from importlib.resources import files
from pathlib import Path

__all__ = ["install_standard", "install_claude", "install_codex", "find_project_root"]

# Markers for detecting project root
_ROOT_MARKERS = (".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml")

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)---\s*\n", re.DOTALL)
_FM_FIELD_RE = re.compile(r'^(\w+):\s*"(.+?)"\s*$', re.MULTILINE)

# Permissions added to .claude/settings.json
_CLAUDE_PERMISSIONS = [
    "Bash(kenso search:*)",
    "Bash(kenso stats:*)",
    "Bash(kenso lint:*)",
    "Bash(kenso ingest:*)",
]


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


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract fields from YAML frontmatter."""
    match = _FRONTMATTER_RE.search(text)
    if not match:
        return {}
    block = match.group(1)
    return dict(_FM_FIELD_RE.findall(block))


def _collect_skills(
    commands_dir: Path,
) -> list[tuple[str, Path, list[Path]]]:
    """Return list of (skill_name, skill_md, support_files) from *commands_dir*.

    Each ``*.md`` directly in *commands_dir* is a skill.
    Support files come from subdirectories matching the skill name pattern.
    """
    if not commands_dir.is_dir():
        return []

    skills: list[tuple[str, Path, list[Path]]] = []
    for md in sorted(commands_dir.glob("*.md")):
        skill_name = md.stem  # e.g. "kenso-ask"
        # Check for a matching subdirectory with support files
        support: list[Path] = []
        skill_subdir = commands_dir / skill_name
        if skill_subdir.is_dir():
            support = sorted(f for f in skill_subdir.rglob("*") if f.is_file())
        skills.append((skill_name, md, support))
    return skills


# ── Standard (.agents/skills/) ────────────────────────────────────


def install_standard(root: Path) -> list[str]:
    """Install kenso skills to ``.agents/skills/`` (Agent Skills standard).

    Returns a list of human-readable status lines.
    """
    commands_dir = _canonical_commands_path()
    skills = _collect_skills(commands_dir)

    if not skills:
        return ["No kenso skills found in package."]

    lines: list[str] = []
    new = updated = unchanged = 0

    for skill_name, src_md, support_files in skills:
        skill_dir = root / ".agents" / "skills" / skill_name
        dest = skill_dir / "SKILL.md"
        skill_dir.mkdir(parents=True, exist_ok=True)

        content = src_md.read_text(encoding="utf-8")
        status = _write_status(dest, content)
        lines.append(f"  .agents/skills/{skill_name}/SKILL.md ({status})")
        if status == "new":
            new += 1
        elif status == "updated":
            updated += 1
        else:
            unchanged += 1

        # Support files go into skill subdirectories
        for sf in support_files:
            rel = sf.relative_to(commands_dir / skill_name)
            dest_sf = skill_dir / rel
            dest_sf.parent.mkdir(parents=True, exist_ok=True)
            _write_status(dest_sf, sf.read_text(encoding="utf-8"))

    total = new + updated
    summary = (
        f"{total} skill{'s' if total != 1 else ''} installed to .agents/skills/"
        if total
        else "Skills in .agents/skills/ unchanged."
    )
    return [summary, *lines]


# ── Claude Code (.claude/) ────────────────────────────────────────


def install_claude(root: Path) -> list[str]:
    """Install kenso skills for Claude Code.

    Creates:
    - ``.claude/commands/kenso/`` — thin slash-command wrappers
    - ``.claude/skills/`` — full skill directories
    - ``.claude/settings.json`` — CLI permissions

    Returns a list of human-readable status lines.
    """
    commands_dir = _canonical_commands_path()
    skills = _collect_skills(commands_dir)

    if not skills:
        return ["No kenso skills found in package."]

    lines: list[str] = []
    cmd_new = cmd_updated = cmd_unchanged = 0
    skill_new = skill_updated = skill_unchanged = 0

    for skill_name, src_md, support_files in skills:
        # Short name for the slash command (kenso-ask → ask)
        short_name = skill_name.removeprefix("kenso-")
        raw = src_md.read_text(encoding="utf-8")
        fm = _parse_frontmatter(raw)
        description = fm.get("description", f"Kenso {short_name} skill")

        # ── Slash command wrapper ──
        cmd_dir = root / ".claude" / "commands" / "kenso"
        cmd_dir.mkdir(parents=True, exist_ok=True)
        cmd_dest = cmd_dir / f"{short_name}.md"
        wrapper = (
            f"{description}\n"
            f"\n"
            f"Load and follow the instructions from @.claude/skills/{skill_name}/SKILL.md\n"
            f"\n"
            f"Use the user's question: $ARGUMENTS\n"
        )
        status = _write_status(cmd_dest, wrapper)
        lines.append(f"  .claude/commands/kenso/{short_name}.md ({status})")
        if status == "new":
            cmd_new += 1
        elif status == "updated":
            cmd_updated += 1
        else:
            cmd_unchanged += 1

        # ── Full skill ──
        skill_dir = root / ".claude" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_dest = skill_dir / "SKILL.md"
        status = _write_status(skill_dest, raw)
        lines.append(f"  .claude/skills/{skill_name}/SKILL.md ({status})")
        if status == "new":
            skill_new += 1
        elif status == "updated":
            skill_updated += 1
        else:
            skill_unchanged += 1

        # Support files into skill directory
        for sf in support_files:
            rel = sf.relative_to(commands_dir / skill_name)
            dest_sf = skill_dir / rel
            dest_sf.parent.mkdir(parents=True, exist_ok=True)
            _write_status(dest_sf, sf.read_text(encoding="utf-8"))

    # ── Permissions ──
    perm_status = _update_claude_settings(root)
    lines.append(f"  .claude/settings.json ({perm_status})")

    total_cmd = cmd_new + cmd_updated
    total_skill = skill_new + skill_updated
    if total_cmd or total_skill:
        summary = (
            f"{total_cmd} command{'s' if total_cmd != 1 else ''} + "
            f"{total_skill} skill{'s' if total_skill != 1 else ''} "
            f"installed to .claude/"
        )
    else:
        summary = "Skills in .claude/ unchanged."
    return [summary, *lines]


def _update_claude_settings(root: Path) -> str:
    """Add kenso permissions to ``.claude/settings.json``.

    Returns 'new', 'updated', or 'unchanged'.
    """
    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            settings = {}
    else:
        settings = {}

    permissions = settings.get("permissions", {})
    allow = permissions.get("allow", [])

    added = 0
    for perm in _CLAUDE_PERMISSIONS:
        if perm not in allow:
            allow.append(perm)
            added += 1

    if added == 0:
        return "unchanged"

    permissions["allow"] = allow
    settings["permissions"] = permissions
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return f"{added} permissions added" if not settings_path.exists() or added > 0 else "unchanged"


# ── Codex CLI (.codex/skills/) ────────────────────────────────────


def install_codex(root: Path) -> list[str]:
    """Install kenso skills for Codex CLI (legacy).

    Returns a list of human-readable status lines.
    """
    commands_dir = _canonical_commands_path()
    skills = _collect_skills(commands_dir)

    if not skills:
        return ["No kenso skills found in package."]

    target_skills = root / ".codex" / "skills"
    lines: list[str] = []
    new = updated = unchanged = 0

    for skill_name, src_md, support_files in skills:
        skill_dir = target_skills / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        dest = skill_dir / "SKILL.md"

        content = src_md.read_text(encoding="utf-8")
        status = _write_status(dest, content)
        lines.append(f"  .codex/skills/{skill_name}/SKILL.md ({status})")
        if status == "new":
            new += 1
        elif status == "updated":
            updated += 1
        else:
            unchanged += 1

        # Support files into skill directory
        for sf in support_files:
            rel = sf.relative_to(commands_dir / skill_name)
            dest_sf = skill_dir / rel
            dest_sf.parent.mkdir(parents=True, exist_ok=True)
            _write_status(dest_sf, sf.read_text(encoding="utf-8"))

    total = new + updated
    summary = (
        f"{total} skill{'s' if total != 1 else ''} installed to .codex/skills/"
        if total
        else "Skills in .codex/skills/ unchanged."
    )
    return [summary, *lines]


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
