"""Lint markdown files for retrieval quality issues."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from kenso.ingest import (
    _H1_RE,
    _H2_RE,
    extract_title,
    parse_frontmatter,
    scan_files,
)

__all__ = ["lint_path", "format_summary", "format_detail", "format_json"]

# ── Rule definitions ────────────────────────────────────────────────

_GENERIC_TITLES = frozenset(
    w.lower()
    for w in [
        "Overview",
        "Guide",
        "Notes",
        "README",
        "Introduction",
        "Summary",
        "Documentation",
        "Index",
        "Main",
        "Home",
        "About",
        "Info",
        "Details",
        "Misc",
        "Draft",
        "Untitled",
        "TODO",
        "WIP",
    ]
)

_GENERIC_HEADINGS = frozenset(
    w.lower()
    for w in [
        "Configuration",
        "Setup",
        "Details",
        "Notes",
        "Overview",
        "Examples",
        "Usage",
        "Summary",
        "Background",
        "Context",
        "Description",
        "Implementation",
        "Results",
        "Discussion",
        "Conclusion",
        "References",
        "Appendix",
        "Changelog",
        "FAQ",
        "Troubleshooting",
        "Prerequisites",
        "Requirements",
        "Installation",
        "Getting Started",
    ]
)

_WEAK_LEAD_PREFIXES = [
    "this section",
    "in this section",
    "the following",
    "below is",
    "here we",
    "this document",
    "this page",
    "as mentioned",
]

_DANGLING_PRONOUNS = ["It ", "This ", "These ", "Those ", "They "]

# Stem suffixes for KS013 (rough heuristic, not a full Porter stemmer)
_STEM_SUFFIXES = [
    "tion",
    "ment",
    "ing",
    "est",
    "ed",
    "ly",
    "er",
    "es",
    "s",
]


@dataclass
class Violation:
    rule: str
    severity: str  # "error", "warning", "info"
    name: str
    message: str


@dataclass
class FileResult:
    path: str
    score: int
    violations: list[Violation] = field(default_factory=list)


@dataclass
class LintResult:
    score: int
    files: int
    errors: int
    warnings: int
    info: int
    file_results: list[FileResult] = field(default_factory=list)


# ── Score deductions ────────────────────────────────────────────────

_DEDUCTIONS: dict[str, float] = {
    "KS004": 18,
    "KS005": 18,
    "KS008": 14,
    "KS003": 12,
    "KS007": 6,  # per heading, max 14
    "KS006": 4,
    "KS012": 4,
    "KS011": 2,
    "KS009": 2,  # per section, max 6
}

# Impact percentages for summary table (theoretical max improvement)
_IMPACT: dict[str, int] = {
    "KS004": 18,
    "KS005": 18,
    "KS003": 12,
    "KS008": 8,
    "KS007": 6,
    "KS006": 4,
    "KS012": 3,
    "KS002": 1,
    "KS017": 1,
    "KS001": 1,
    "KS010": 1,
    "KS014": 1,
    "KS018": 1,
    "KS019": 3,
}

_RULE_LABELS: dict[str, str] = {
    "KS001": "Remove or expand too-short files",
    "KS002": "Fix broken relates_to links",
    "KS003": "Add tags to frontmatter",
    "KS004": "Add a descriptive title",
    "KS005": "Make title more specific",
    "KS006": "Add preamble before first H2",
    "KS007": "Make H2 headings more specific",
    "KS008": "Add H2 headings for section chunking",
    "KS009": "Split oversized sections",
    "KS010": "Expand tiny H2 sections",
    "KS011": "Add more tags (3+ recommended)",
    "KS012": "Add relates_to links",
    "KS013": "Remove redundant tags",
    "KS014": "Fix inconsistent category name",
    "KS015": "Improve section lead sentences",
    "KS016": "Avoid dangling pronouns in sections",
    "KS017": "Remove glob patterns from relates_to",
    "KS018": "Reduce relates_to entries (max 10)",
    "KS019": "Add missing relates_to links",
}


def _compute_file_score(violations: list[Violation]) -> int:
    score = 100.0
    ks007_count = 0
    ks009_count = 0
    ks019_count = 0

    for v in violations:
        if v.rule in ("KS004", "KS005"):
            # Only deduct once for title issues (they're mutually exclusive in practice,
            # but cap at 18 regardless)
            score -= _DEDUCTIONS.get(v.rule, 0)
        elif v.rule == "KS007":
            old_total = min(ks007_count * 6, 14)
            ks007_count += 1
            new_total = min(ks007_count * 6, 14)
            score -= new_total - old_total
        elif v.rule == "KS009":
            old_total = min(ks009_count * 2, 6)
            ks009_count += 1
            new_total = min(ks009_count * 2, 6)
            score -= new_total - old_total
        elif v.rule == "KS019":
            old_total = min(ks019_count * 1, 4)
            ks019_count += 1
            new_total = min(ks019_count * 1, 4)
            score -= new_total - old_total
        elif v.rule in _DEDUCTIONS:
            score -= _DEDUCTIONS[v.rule]
        elif v.severity == "warning":
            score -= 1
        elif v.severity == "info":
            score -= 0.5
        elif v.severity == "error":
            score -= 3

    return max(0, int(round(score)))


# ── Helpers ─────────────────────────────────────────────────────────


def _rough_stem(word: str) -> str:
    """Rough suffix-stripping stemmer for KS013."""
    w = word.lower()
    for suffix in _STEM_SUFFIXES:
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    return w


def _extract_h2_sections(body: str) -> list[tuple[str, str]]:
    """Extract (heading_text, section_content) pairs from body text."""
    matches = list(_H2_RE.finditer(body))
    if not matches:
        return []
    sections = []
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        sections.append((heading, content))
    return sections


def _first_content_line(text: str) -> str:
    """Return the first non-empty, non-heading line of a section."""
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def _strip_code(text: str) -> str:
    """Strip fenced code blocks and inline code from text."""
    # Strip fenced code blocks (``` or ~~~)
    result = re.sub(r"^(`{3,}|~{3,}).*?^\1", "", text, flags=re.MULTILINE | re.DOTALL)
    # Strip inline code
    result = re.sub(r"`[^`]+`", "", result)
    return result


def _has_yaml() -> bool:
    """Check if PyYAML is available."""
    try:
        import yaml  # noqa: F401

        return True
    except ImportError:
        return False


def _extract_relates_to_raw(text: str) -> list[str] | None:
    """Extract raw relates_to paths from frontmatter.

    Returns None if PyYAML is needed but not installed.
    Returns an empty list if no relates_to field exists.
    """
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end == -1:
        return []

    fm_block = text[4:end]

    # Try YAML first
    try:
        import yaml

        meta = yaml.safe_load(fm_block)
        if not isinstance(meta, dict):
            return []
        raw = meta.get("relates_to")
        if raw is None:
            return []
        paths: list[str] = []
        if isinstance(raw, str):
            paths = [v.strip() for v in raw.split(",") if v.strip()]
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    paths.append(item.strip())
                elif isinstance(item, dict):
                    p = str(item.get("path", "")).strip()
                    if p:
                        paths.append(p)
        return paths
    except ImportError:
        # Check if relates_to uses complex YAML (list of dicts)
        if re.search(r"^\s+- path:", fm_block, re.MULTILINE):
            return None  # Need PyYAML
        # Simple format: try regex fallback
        paths = []
        lines = fm_block.split("\n")
        in_list = False
        for line in lines:
            m = re.match(r"^relates_to\s*:\s*(.+)$", line)
            if m:
                val = m.group(1).strip()
                if val:
                    paths.extend(v.strip().strip("\"'- ") for v in val.split(",") if v.strip())
                continue
            if re.match(r"^relates_to\s*:\s*$", line):
                in_list = True
                continue
            if in_list:
                item = re.match(r"^\s+-\s+(.+)$", line)
                if item:
                    paths.append(item.group(1).strip().strip("\"'"))
                elif line.strip():
                    in_list = False
        return paths
    except Exception:
        return []


# ── Per-file rules ──────────────────────────────────────────────────


def _check_file(
    rel_path: str,
    text: str,
    *,
    all_paths: set[str],
    link_sources: set[str],
    link_targets: set[str],
    category_counts: dict[str, int],
    all_categories: list[str],
    chunk_size: int,
    yaml_available: bool,
    title_patterns: list[tuple[re.Pattern[str], str, str]] | None = None,
) -> list[Violation]:
    """Run all lint rules against a single file."""
    violations: list[Violation] = []
    frontmatter, body = parse_frontmatter(text)

    # ── Errors ──────────────────────────────────────────────────────

    # KS001: file-too-short
    if len(text.strip()) < 50:
        violations.append(
            Violation("KS001", "error", "file-too-short", "File has fewer than 50 characters")
        )

    # KS002 & KS017: broken-link and glob-in-link
    relates_paths = _extract_relates_to_raw(text)
    if relates_paths is None:
        # PyYAML needed but not installed — skip link rules
        pass
    elif relates_paths:
        for p in relates_paths:
            if "*" in p or "?" in p:
                violations.append(
                    Violation(
                        "KS017",
                        "error",
                        "glob-in-link",
                        f'relates_to "{p}" contains glob characters',
                    )
                )
            elif p not in all_paths:
                violations.append(
                    Violation(
                        "KS002",
                        "error",
                        "broken-link",
                        f'relates_to "{p}" not found',
                    )
                )

    # KS010: tiny-section
    h2_sections = _extract_h2_sections(body)
    for heading, content in h2_sections:
        if len(content.strip()) < 20:
            violations.append(
                Violation(
                    "KS010",
                    "error",
                    "tiny-section",
                    f'H2 "{heading}" has fewer than 20 characters of content',
                )
            )

    # ── Warnings ────────────────────────────────────────────────────

    # Resolve tags
    raw_tags = frontmatter.get("tags", "")
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str) and raw_tags:
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = []

    # KS003: missing-tags
    if not tags:
        violations.append(Violation("KS003", "warning", "missing-tags", "No tags in frontmatter"))

    # Resolve title
    h1_title = extract_title(body)
    fm_title = frontmatter.get("title")
    resolved_title = h1_title or (fm_title if isinstance(fm_title, str) else None)

    # KS004: missing-title
    if not resolved_title:
        violations.append(
            Violation(
                "KS004",
                "warning",
                "missing-title",
                "No H1 heading and no title in frontmatter",
            )
        )

    # KS005: generic-title
    display_title = resolved_title or Path(rel_path).stem
    if resolved_title:
        title_words = resolved_title.strip().split()
        if len(title_words) == 1 or resolved_title.strip().lower() in _GENERIC_TITLES:
            violations.append(
                Violation(
                    "KS005",
                    "warning",
                    "generic-title",
                    f'Title "{resolved_title}" is too generic',
                )
            )

    # KS006: no-preamble
    if h2_sections:
        first_h2 = _H2_RE.search(body)
        if first_h2:
            preamble = body[: first_h2.start()]
            # Remove H1 from preamble
            preamble = _H1_RE.sub("", preamble).strip()
            if len(preamble) < 50:
                violations.append(
                    Violation(
                        "KS006",
                        "warning",
                        "no-preamble",
                        "No content (or < 50 chars) before first H2",
                    )
                )

    # KS007: generic-heading
    for heading, _ in h2_sections:
        h_words = heading.strip().split()
        if len(h_words) == 1 or heading.strip().lower() in _GENERIC_HEADINGS:
            violations.append(
                Violation(
                    "KS007",
                    "warning",
                    "generic-heading",
                    f'H2 "{heading}" — consider a more specific heading',
                )
            )

    # KS008: no-h2
    if not h2_sections and len(body.strip()) > 500:
        violations.append(
            Violation(
                "KS008",
                "warning",
                "no-h2",
                "No H2 headings — entire document will be a single chunk",
            )
        )

    # KS012: orphan-doc
    if rel_path not in link_sources and rel_path not in link_targets:
        violations.append(
            Violation(
                "KS012",
                "warning",
                "orphan-doc",
                "No relates_to links and not referenced by other documents",
            )
        )

    # KS014: inconsistent-category
    category = frontmatter.get("category") or (
        str(Path(rel_path).parent) if str(Path(rel_path).parent) != "." else "general"
    )
    if isinstance(category, str) and category_counts.get(category, 0) == 1:
        other_categories = [c for c in all_categories if c != category]
        similar = difflib.get_close_matches(category, other_categories, n=1, cutoff=0.6)
        if similar:
            violations.append(
                Violation(
                    "KS014",
                    "warning",
                    "inconsistent-category",
                    f'Category "{category}" used by only this file — did you mean "{similar[0]}"?',
                )
            )

    # KS018: too-many-links
    if relates_paths and len(relates_paths) > 10:
        violations.append(
            Violation(
                "KS018",
                "warning",
                "too-many-links",
                f"relates_to has {len(relates_paths)} entries (max recommended: 10)",
            )
        )

    # KS019: unlinked-mention
    if title_patterns:
        linked_paths = set(relates_paths) if relates_paths else set()
        clean_body = _strip_code(body)
        for pattern, matched_text, target_path in title_patterns:
            if target_path == rel_path:
                continue
            if target_path in linked_paths:
                continue
            if pattern.search(clean_body):
                violations.append(
                    Violation(
                        "KS019",
                        "warning",
                        "unlinked-mention",
                        f'Body mentions "{matched_text}" \u2192 {target_path}',
                    )
                )

    # ── Info ────────────────────────────────────────────────────────

    # KS009: oversized-section
    for heading, content in h2_sections:
        section_len = len(content)
        if section_len > chunk_size:
            violations.append(
                Violation(
                    "KS009",
                    "info",
                    "oversized-section",
                    f'"{heading}" is {section_len:,} chars (max {chunk_size:,})',
                )
            )

    # KS011: few-tags
    if tags and len(tags) < 3:
        violations.append(
            Violation(
                "KS011",
                "info",
                "few-tags",
                f"Only {len(tags)} tag(s) — 3+ recommended for synonym coverage",
            )
        )

    # KS013: redundant-tag
    if tags and display_title:
        title_stems = {_rough_stem(w) for w in display_title.split() if len(w) >= 3}
        for tag in tags:
            tag_stem = _rough_stem(tag)
            if tag_stem in title_stems:
                violations.append(
                    Violation(
                        "KS013",
                        "info",
                        "redundant-tag",
                        f'Tag "{tag}" overlaps with title word (stemmer handles this)',
                    )
                )

    # KS015: weak-lead
    for heading, content in h2_sections:
        first_line = _first_content_line(content).lower()
        for prefix in _WEAK_LEAD_PREFIXES:
            if first_line.startswith(prefix):
                violations.append(
                    Violation(
                        "KS015",
                        "info",
                        "weak-lead",
                        f'"{heading}" starts with boilerplate ("{prefix}...")',
                    )
                )
                break

    # KS016: dangling-pronoun
    for heading, content in h2_sections:
        first_line = _first_content_line(content)
        for pronoun in _DANGLING_PRONOUNS:
            if first_line.startswith(pronoun):
                violations.append(
                    Violation(
                        "KS016",
                        "info",
                        "dangling-pronoun",
                        f'"{heading}" starts with "{pronoun.strip()}" — may not be self-contained',
                    )
                )
                break

    return violations


# ── Main entry point ────────────────────────────────────────────────


def lint_path(root: str, *, chunk_size: int = 4000) -> LintResult:
    """Lint markdown files under root for retrieval quality issues."""
    root_path = Path(root).resolve()
    if not root_path.exists():
        return LintResult(score=100, files=0, errors=0, warnings=0, info=0)

    files = scan_files(root_path)
    if not files:
        return LintResult(score=100, files=0, errors=0, warnings=0, info=0)

    base = root_path.parent if root_path.is_file() else root_path
    yaml_available = _has_yaml()

    # ── First pass: collect cross-file metadata ─────────────────────
    file_data: list[tuple[str, str]] = []  # (rel_path, text)
    all_paths: set[str] = set()
    link_sources: set[str] = set()
    link_targets: set[str] = set()
    category_counts: dict[str, int] = {}
    yaml_warning_shown = False

    for f in files:
        rel = str(f.relative_to(base))
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        all_paths.add(rel)
        file_data.append((rel, text))

        # Collect relates_to for orphan detection
        relates = _extract_relates_to_raw(text)
        if relates is None:
            if not yaml_warning_shown:
                yaml_warning_shown = True
            relates = []
        if relates:
            link_sources.add(rel)
            for p in relates:
                if "*" not in p and "?" not in p:
                    link_targets.add(p)

        # Collect category for consistency check
        fm, _ = parse_frontmatter(text)
        category = fm.get("category") or (
            str(Path(rel).parent) if str(Path(rel).parent) != "." else "general"
        )
        if isinstance(category, str):
            category_counts[category] = category_counts.get(category, 0) + 1

    all_categories = list(category_counts.keys())

    # Build title/alias lookup for KS019 (unlinked-mention)
    # Each entry: (compiled_regex, display_text, target_rel_path)
    title_patterns: list[tuple[re.Pattern[str], str, str]] = []
    for rel, text in file_data:
        fm, body = parse_frontmatter(text)
        # Collect title
        h1 = extract_title(body)
        fm_title = fm.get("title")
        doc_title = h1 or (fm_title if isinstance(fm_title, str) else None) or Path(rel).stem
        # Collect aliases
        raw_aliases = fm.get("aliases")
        aliases = [str(a) for a in raw_aliases] if isinstance(raw_aliases, list) else []
        # Build patterns for title and aliases
        for label in [doc_title] + aliases:
            normalized = " ".join(label.split())
            if len(normalized) <= 3:
                continue
            escaped = re.escape(normalized)
            try:
                pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
            except re.error:
                continue
            title_patterns.append((pattern, normalized, rel))

    # ── Second pass: run rules ──────────────────────────────────────
    file_results: list[FileResult] = []
    total_errors = 0
    total_warnings = 0
    total_info = 0

    for rel_path, text in file_data:
        violations = _check_file(
            rel_path,
            text,
            all_paths=all_paths,
            link_sources=link_sources,
            link_targets=link_targets,
            category_counts=category_counts,
            all_categories=all_categories,
            chunk_size=chunk_size,
            yaml_available=yaml_available,
            title_patterns=title_patterns,
        )

        file_score = _compute_file_score(violations)

        for v in violations:
            if v.severity == "error":
                total_errors += 1
            elif v.severity == "warning":
                total_warnings += 1
            else:
                total_info += 1

        file_results.append(FileResult(path=rel_path, score=file_score, violations=violations))

    # Overall score = average of file scores
    if file_results:
        overall_score = round(sum(fr.score for fr in file_results) / len(file_results))
    else:
        overall_score = 100

    return LintResult(
        score=overall_score,
        files=len(file_results),
        errors=total_errors,
        warnings=total_warnings,
        info=total_info,
        file_results=file_results,
    )


# ── Output formatters ──────────────────────────────────────────────

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def format_summary(result: LintResult) -> str:
    """Format lint result as summary output."""
    lines = [f"\nScore: {result.score}/100 ({result.files} files)\n"]

    # Collect violation counts per rule
    rule_counts: dict[str, int] = {}
    for fr in result.file_results:
        seen_rules: set[str] = set()
        for v in fr.violations:
            if v.rule not in seen_rules:
                rule_counts[v.rule] = rule_counts.get(v.rule, 0) + 1
                seen_rules.add(v.rule)

    if not rule_counts:
        lines.append("All checks passed.")
        return "\n".join(lines)

    # Sort by impact (descending), then rule ID
    sorted_rules = sorted(
        rule_counts.keys(),
        key=lambda r: (-_IMPACT.get(r, 0), r),
    )

    # Build table
    lines.append("  What to fix first                          Files   Impact")
    lines.append("  " + "─" * 55)

    for rule in sorted_rules:
        label = _RULE_LABELS.get(rule, rule)
        count = rule_counts[rule]
        impact = _IMPACT.get(rule, 0)
        impact_str = f"+{impact}%" if impact else ""
        lines.append(f"  {label:<37} ({rule}) {count:>3}   {impact_str:>5}")

    lines.append("")
    lines.append(
        f"  {result.errors} errors · {result.warnings} warnings · {result.info} suggestions"
    )
    lines.append("")
    lines.append("  Run kenso lint --detail to see per-file results.")

    return "\n".join(lines)


def format_detail(result: LintResult) -> str:
    """Format lint result as per-file detail output."""
    lines: list[str] = []

    for fr in result.file_results:
        if not fr.violations:
            continue

        lines.append(f"\n{fr.path} (score: {fr.score}/100)")

        # Sort by severity then rule ID
        sorted_violations = sorted(
            fr.violations,
            key=lambda v: (_SEVERITY_ORDER.get(v.severity, 9), v.rule),
        )

        for v in sorted_violations:
            lines.append(f"  {v.rule} {v.severity:<8} {v.name:<20} {v.message}")

    if lines:
        lines.append("")
    lines.append(f"Score: {result.score}/100 ({result.files} files)")
    lines.append(
        f"{result.errors} errors · {result.warnings} warnings · {result.info} suggestions"
    )

    return "\n".join(lines)


def format_ingest_summary(result: LintResult) -> str:
    """Format lint result as a compact summary for ingest output."""
    files_with_issues = sum(1 for fr in result.file_results if fr.violations)

    lines = [f"  Quality Score: {result.score}/100"]

    # Collect violation counts per rule
    rule_counts: dict[str, int] = {}
    for fr in result.file_results:
        seen_rules: set[str] = set()
        for v in fr.violations:
            if v.rule not in seen_rules:
                rule_counts[v.rule] = rule_counts.get(v.rule, 0) + 1
                seen_rules.add(v.rule)

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
            lines.append(f"    {label:<37} ({rule}) {count:>3}   {impact_str:>5}")

    if files_with_issues:
        lines.append(
            f"  {files_with_issues} files with issues. Run kenso lint --detail for specifics."
        )
    else:
        lines.append("  All checks passed.")

    return "\n".join(lines)


def format_json(result: LintResult) -> str:
    """Format lint result as JSON output."""
    violations_list = []
    for fr in result.file_results:
        if not fr.violations:
            continue
        issues = [
            {
                "rule": v.rule,
                "severity": v.severity,
                "name": v.name,
                "message": v.message,
            }
            for v in fr.violations
        ]
        violations_list.append(
            {
                "file": fr.path,
                "score": fr.score,
                "issues": issues,
            }
        )

    output = {
        "score": result.score,
        "files": result.files,
        "summary": {
            "errors": result.errors,
            "warnings": result.warnings,
            "info": result.info,
        },
        "violations": violations_list,
    }
    return json.dumps(output, indent=2)
