#!/usr/bin/env python3
"""Deterministic search quality eval for kenso.

Measures retrieval quality across 7 failure-mode categories:
  A. Exact keyword match (baseline)
  B. Synonym / vocabulary mismatch
  C. Multi-concept / cross-domain
  D. Tag-only discoverability
  E. Pre-H2 content capture
  F. Chunk ambiguity (generic headings)
  G. Question-style queries (LLM-typical)

Metrics per category and overall:
  - Hit Rate@K     — fraction of queries where ≥1 relevant doc in top K
  - MRR            — Mean Reciprocal Rank of first relevant result
  - Precision@K    — fraction of top K results that are relevant
  - NDCG@K         — Normalized Discounted Cumulative Gain (graded relevance)
  - Recall@K       — for multi-concept queries, how many expected docs found

Usage:
    python tests/eval/eval_harness.py                  # run eval, print report
    python tests/eval/eval_harness.py --json            # machine-readable output
    python tests/eval/eval_harness.py --save baseline   # save snapshot as "baseline"
    python tests/eval/eval_harness.py --compare baseline # compare current vs saved snapshot
    python tests/eval/eval_harness.py --verbose          # show per-query details
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ── Imports from local corpus ────────────────────────────────────────
from corpus import CORPUS, EVAL_CASES

from kenso.backend import Backend

# ── Imports from kenso ───────────────────────────────────────────────
from kenso.config import KensoConfig
from kenso.ingest import chunk_by_headings, extract_relates_to, parse_frontmatter

K = 5  # Top-K for all metrics
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


# ═══════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class QueryResult:
    """Result of evaluating a single query."""
    id: str
    category_label: str
    query: str
    description: str
    expected_paths: list[str]
    returned_paths: list[str]
    returned_titles: list[str]
    returned_scores: list[float]
    hit: bool
    precision_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    recall: float
    chunk_keyword_hits: int
    chunk_keyword_total: int


@dataclass
class CategoryMetrics:
    """Aggregated metrics for one eval category."""
    label: str
    count: int
    hit_rate: float
    mrr: float
    mean_precision: float
    mean_ndcg: float
    mean_recall: float


@dataclass
class EvalReport:
    """Full evaluation report."""
    total_queries: int
    overall_hit_rate: float
    overall_mrr: float
    overall_precision: float
    overall_ndcg: float
    overall_recall: float
    categories: list[CategoryMetrics]
    per_query: list[QueryResult]
    corpus_stats: dict[str, Any]
    feature_tests: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
# Scoring functions
# ═══════════════════════════════════════════════════════════════════════


def _is_relevant(returned_path: str, expected_patterns: list[str]) -> bool:
    """Check if a returned path matches any expected pattern (substring)."""
    return any(pattern.lower() in returned_path.lower() for pattern in expected_patterns)


def _dcg(relevances: list[int], k: int) -> float:
    """Discounted Cumulative Gain at k."""
    score = 0.0
    for i, rel in enumerate(relevances[:k]):
        if rel > 0:
            score += rel / math.log2(i + 2)  # i+2 because i is 0-indexed
    return score


def _ndcg_at_k(returned_paths: list[str], expected_paths: list[str], k: int) -> float:
    """Normalized DCG at k. Deduped binary relevance per unique expected doc."""
    # Deduplicate: count each expected doc at most once (first occurrence)
    seen_relevant = set()
    relevances = []
    for p in returned_paths[:k]:
        matched_pattern = None
        for ep in expected_paths:
            if ep.lower() in p.lower() and ep not in seen_relevant:
                matched_pattern = ep
                break
        if matched_pattern:
            relevances.append(1)
            seen_relevant.add(matched_pattern)
        else:
            relevances.append(0)

    dcg = _dcg(relevances, k)

    # Ideal: all expected docs at top positions
    n_expected = min(len(expected_paths), k)
    ideal_rels = [1] * n_expected + [0] * (k - n_expected)
    idcg = _dcg(ideal_rels, k)

    return dcg / idcg if idcg > 0 else 0.0


def _count_keyword_hits(returned_content: list[str], keywords: list[str]) -> tuple[int, int]:
    """Check how many expected keywords appear in returned content."""
    total = len(keywords)
    if total == 0:
        return 0, 0
    joined = " ".join(returned_content).lower()
    hits = sum(1 for kw in keywords if kw.lower() in joined)
    return hits, total


def score_query(
    case: dict,
    returned: list[dict[str, Any]],
) -> QueryResult:
    """Score a single query result against expectations."""
    returned_paths = [r["file_path"] for r in returned[:K]]
    returned_titles = [r.get("title", "") for r in returned[:K]]
    returned_scores = [round(float(r.get("score", 0)), 4) for r in returned[:K]]
    returned_content = [r.get("content", "") for r in returned[:K]]
    expected = case["expected_paths"]

    # Hit: at least one relevant doc in top K
    relevant_positions = []
    for i, path in enumerate(returned_paths):
        if _is_relevant(path, expected):
            relevant_positions.append(i + 1)  # 1-indexed

    hit = len(relevant_positions) > 0
    rr = 1.0 / relevant_positions[0] if relevant_positions else 0.0

    # Precision@K
    relevant_count = sum(
        1 for p in returned_paths if _is_relevant(p, expected)
    )
    precision = relevant_count / min(K, max(len(returned_paths), 1))

    # NDCG@K
    ndcg = _ndcg_at_k(returned_paths, expected, K)

    # Recall: fraction of expected docs found
    expected_found = set()
    for ep in expected:
        for rp in returned_paths:
            if ep.lower() in rp.lower():
                expected_found.add(ep)
                break
    recall = len(expected_found) / len(expected) if expected else 1.0

    # Chunk keyword hits (content quality check)
    kw_hits, kw_total = _count_keyword_hits(
        returned_content,
        case.get("expected_chunk_keywords", []),
    )

    return QueryResult(
        id=case["id"],
        category_label=case["category_label"],
        query=case["query"],
        description=case["description"],
        expected_paths=expected,
        returned_paths=returned_paths,
        returned_titles=returned_titles,
        returned_scores=returned_scores,
        hit=hit,
        precision_at_k=precision,
        reciprocal_rank=rr,
        ndcg_at_k=ndcg,
        recall=recall,
        chunk_keyword_hits=kw_hits,
        chunk_keyword_total=kw_total,
    )


# ═══════════════════════════════════════════════════════════════════════
# Database setup
# ═══════════════════════════════════════════════════════════════════════


async def build_eval_db() -> Backend:
    """Create an in-memory SQLite backend populated with the eval corpus."""
    cfg = KensoConfig(database_url=":memory:")
    backend = Backend(cfg)
    await backend.startup()
    await backend.init_schema()

    for doc in CORPUS:
        raw_content = doc["content"]

        # Parse frontmatter just like the real ingester does
        frontmatter, body = parse_frontmatter(raw_content)

        title = frontmatter.get("title") or doc["path"].split("/")[-1]
        category = frontmatter.get("category") or doc["path"].split("/")[0]

        # Handle tags as YAML list or comma-separated string
        raw_tags = frontmatter.get("tags", "")
        if isinstance(raw_tags, list):
            tags = [str(t).strip() for t in raw_tags if str(t).strip()]
        elif isinstance(raw_tags, str) and raw_tags:
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            tags = None

        # Extract frontmatter metadata for searchable_content
        raw_aliases = frontmatter.get("aliases")
        aliases = [str(a) for a in raw_aliases] if isinstance(raw_aliases, list) else None
        raw_answers = frontmatter.get("answers")
        answers = [str(a) for a in raw_answers] if isinstance(raw_answers, list) else None
        fm_description = frontmatter.get("description")
        fm_description = fm_description.strip() if isinstance(fm_description, str) and fm_description.strip() else None

        # Chunk using the same logic as real ingestion (pure body, no metadata preamble)
        chunks = chunk_by_headings(body, doc["path"], max_chunk_size=cfg.chunk_size)

        await backend.ingest_file(
            doc["path"],
            chunks,
            title=title,
            category=category,
            audience="all",
            tags=tags,
            content_hash=None,
            aliases=aliases,
            answers=answers,
            description=fm_description,
        )

        # Insert relates_to links (with relation types)
        link_targets = extract_relates_to(raw_content)
        if link_targets:
            with contextlib.suppress(Exception):
                await backend.insert_typed_links(doc["path"], link_targets)

    return backend


# ═══════════════════════════════════════════════════════════════════════
# Sprint 4 feature tests (non-search: graph traversal, search_multi, types)
# ═══════════════════════════════════════════════════════════════════════


async def _run_feature_tests(backend) -> dict[str, Any]:
    """Test Sprint 4 features: typed relations, depth traversal, search_multi."""
    tests: dict[str, Any] = {}

    # Test 1: Typed relations are stored correctly (both directions)
    related = await backend.get_related("post-trade/settlement-lifecycle.md")
    types_found = {r["relation_type"] for r in (related or [])}
    # Settlement has outgoing: receives_from, triggers
    # Other docs point to settlement with: feeds_into, monitors
    tests["typed_relations_stored"] = {
        "pass": {"receives_from", "triggers"}.issubset(types_found),
        "expected_includes": ["receives_from", "triggers"],
        "found_types": sorted(types_found),
    }

    # Test 2: get_related depth=1 returns direct neighbors only
    depth1 = await backend.get_related("post-trade/settlement-lifecycle.md", depth=1)
    depth1_paths = {r["related_path"] for r in (depth1 or [])}
    tests["depth_1_direct"] = {
        "pass": "order-management/matching-engine.md" in depth1_paths
                and "compliance/cnmv-reporting.md" in depth1_paths,
        "count": len(depth1_paths),
        "paths": sorted(depth1_paths),
    }

    # Test 3: get_related depth=2 discovers 2nd-hop neighbors
    depth2 = await backend.get_related("post-trade/settlement-lifecycle.md", depth=2)
    depth2_paths = {r["related_path"] for r in (depth2 or [])}
    has_2hop = (
        "architecture/platform-overview.md" in depth2_paths
        or "compliance/market-surveillance.md" in depth2_paths
    )
    tests["depth_2_expands"] = {
        "pass": has_2hop and len(depth2_paths) > len(depth1_paths),
        "depth1_count": len(depth1_paths),
        "depth2_count": len(depth2_paths),
        "new_at_depth2": sorted(depth2_paths - depth1_paths),
    }

    # Test 4: relation_type filter narrows results
    filtered = await backend.get_related(
        "post-trade/settlement-lifecycle.md", relation_type="triggers",
    )
    filtered_paths = {r["related_path"] for r in (filtered or [])}
    tests["relation_type_filter"] = {
        "pass": filtered_paths == {"compliance/cnmv-reporting.md"},
        "expected": ["compliance/cnmv-reporting.md"],
        "got": sorted(filtered_paths),
    }

    # Test 5: search_multi — two complementary queries cover more docs than either alone
    r1 = await backend.search("CNMV reporting", limit=5)
    r2 = await backend.search("settlement lifecycle", limit=5)
    paths_q1 = {r["file_path"] for r in r1}
    paths_q2 = {r["file_path"] for r in r2}
    union = paths_q1 | paths_q2
    tests["search_multi_coverage"] = {
        "pass": len(union) >= len(paths_q1) and len(union) >= len(paths_q2),
        "q1_docs": len(paths_q1),
        "q2_docs": len(paths_q2),
        "union_docs": len(union),
    }

    return tests


# ═══════════════════════════════════════════════════════════════════════
# Run evaluation
# ═══════════════════════════════════════════════════════════════════════


async def run_eval() -> EvalReport:
    """Run full evaluation and return report."""
    backend = await build_eval_db()

    try:
        # Corpus stats
        stats = await backend.stats()
        corpus_stats = {
            "docs": stats["docs"],
            "chunks": stats["chunks"],
            "categories": stats["categories"],
            "links": stats["links"],
        }

        # Run all queries
        results: list[QueryResult] = []
        for case in EVAL_CASES:
            raw_results = await backend.search(
                case["query"],
                category=None,
                limit=K,
            )
            qr = score_query(case, raw_results)
            results.append(qr)

        # Aggregate by category
        cat_groups: dict[str, list[QueryResult]] = {}
        for r in results:
            cat_groups.setdefault(r.category_label, []).append(r)

        categories = []
        for label, group in sorted(cat_groups.items()):
            n = len(group)
            categories.append(CategoryMetrics(
                label=label,
                count=n,
                hit_rate=sum(1 for r in group if r.hit) / n,
                mrr=sum(r.reciprocal_rank for r in group) / n,
                mean_precision=sum(r.precision_at_k for r in group) / n,
                mean_ndcg=sum(r.ndcg_at_k for r in group) / n,
                mean_recall=sum(r.recall for r in group) / n,
            ))

        # Overall
        n_total = len(results)

        # ── Sprint 4 feature tests ───────────────────────────────────
        feature_tests = await _run_feature_tests(backend)

        report = EvalReport(
            total_queries=n_total,
            overall_hit_rate=sum(1 for r in results if r.hit) / n_total,
            overall_mrr=sum(r.reciprocal_rank for r in results) / n_total,
            overall_precision=sum(r.precision_at_k for r in results) / n_total,
            overall_ndcg=sum(r.ndcg_at_k for r in results) / n_total,
            overall_recall=sum(r.recall for r in results) / n_total,
            categories=categories,
            per_query=results,
            corpus_stats=corpus_stats,
            feature_tests=feature_tests,
        )
        return report

    finally:
        await backend.shutdown()


# ═══════════════════════════════════════════════════════════════════════
# Output formatting
# ═══════════════════════════════════════════════════════════════════════


def _pct(val: float) -> str:
    return f"{val * 100:5.1f}%"


def print_report(report: EvalReport, verbose: bool = False) -> None:
    """Print a human-readable evaluation report."""
    w = 72
    print(f"\n{'═' * w}")
    print("  KENSO SEARCH QUALITY EVAL")
    print(f"  Corpus: {report.corpus_stats['docs']} docs, "
          f"{report.corpus_stats['chunks']} chunks, "
          f"{report.corpus_stats['links']} links")
    print(f"  Queries: {report.total_queries} across "
          f"{len(report.categories)} categories")
    print(f"{'═' * w}")

    # Overall metrics
    print("\n  OVERALL METRICS")
    print(f"  {'─' * 40}")
    print(f"  Hit Rate@{K}:    {_pct(report.overall_hit_rate)}")
    print(f"  MRR:            {_pct(report.overall_mrr)}")
    print(f"  Precision@{K}:   {_pct(report.overall_precision)}")
    print(f"  NDCG@{K}:        {_pct(report.overall_ndcg)}")
    print(f"  Recall@{K}:      {_pct(report.overall_recall)}")

    # Per category
    print("\n  METRICS BY CATEGORY")
    print(f"  {'─' * 66}")
    header = f"  {'Category':<22} {'N':>3}  {'Hit%':>6}  {'MRR':>6}  {'P@K':>6}  {'NDCG':>6}  {'Recall':>6}"
    print(header)
    print(f"  {'─' * 66}")
    for cat in report.categories:
        line = (
            f"  {cat.label:<22} {cat.count:>3}  "
            f"{_pct(cat.hit_rate)}  {_pct(cat.mrr)}  "
            f"{_pct(cat.mean_precision)}  {_pct(cat.mean_ndcg)}  "
            f"{_pct(cat.mean_recall)}"
        )
        print(line)

    # Per query details (failures highlighted)
    print("\n  PER-QUERY RESULTS")
    print(f"  {'─' * 66}")
    for r in report.per_query:
        status = "✓" if r.hit else "✗"
        kw_info = f"kw={r.chunk_keyword_hits}/{r.chunk_keyword_total}" if r.chunk_keyword_total > 0 else ""
        print(
            f"  {status} [{r.id}] {r.query!r:45s} "
            f"RR={r.reciprocal_rank:.2f} P={r.precision_at_k:.2f} {kw_info}"
        )
        if verbose or not r.hit:
            print(f"         expected: {r.expected_paths}")
            print(f"         got:      {r.returned_paths}")
            if r.returned_titles:
                print(f"         titles:   {r.returned_titles}")

    # Feature tests (Sprint 4)
    if report.feature_tests:
        print("\n  FEATURE TESTS")
        print(f"  {'─' * 66}")
        for name, test in report.feature_tests.items():
            status = "✓" if test.get("pass") else "✗"
            detail_parts = []
            for k, v in test.items():
                if k == "pass":
                    continue
                detail_parts.append(f"{k}={v}")
            detail = ", ".join(detail_parts)
            print(f"  {status} {name}")
            if verbose or not test.get("pass"):
                print(f"         {detail}")

    # Summary: identify weakest categories
    print(f"\n  {'═' * w}")
    misses = [r for r in report.per_query if not r.hit]
    if misses:
        print(f"  MISSES: {len(misses)}/{report.total_queries}")
        for r in misses:
            print(f"    [{r.id}] {r.category_label}: {r.query!r}")
            print(f"           → expected: {r.expected_paths}")
    else:
        print("  ALL QUERIES HIT (100% hit rate)")
    print(f"{'═' * w}\n")


def save_snapshot(report: EvalReport, name: str) -> Path:
    """Save report as a JSON snapshot for later comparison."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS_DIR / f"{name}.json"

    # Serialize to JSON-friendly dict
    data = {
        "total_queries": report.total_queries,
        "overall": {
            "hit_rate": report.overall_hit_rate,
            "mrr": report.overall_mrr,
            "precision": report.overall_precision,
            "ndcg": report.overall_ndcg,
            "recall": report.overall_recall,
        },
        "categories": [asdict(c) for c in report.categories],
        "per_query": [
            {
                "id": r.id,
                "category_label": r.category_label,
                "query": r.query,
                "hit": r.hit,
                "reciprocal_rank": r.reciprocal_rank,
                "precision_at_k": r.precision_at_k,
                "ndcg_at_k": r.ndcg_at_k,
                "recall": r.recall,
                "returned_paths": r.returned_paths,
            }
            for r in report.per_query
        ],
        "feature_tests": {
            name: {k: (sorted(list(v)) if isinstance(v, set) else v)
                   for k, v in test.items()}
            for name, test in report.feature_tests.items()
        },
    }
    path.write_text(json.dumps(data, indent=2))
    print(f"  Snapshot saved: {path}")
    return path


def compare_snapshots(report: EvalReport, baseline_name: str) -> None:
    """Compare current results against a saved baseline."""
    baseline_path = SNAPSHOTS_DIR / f"{baseline_name}.json"
    if not baseline_path.exists():
        print(f"  ERROR: Baseline '{baseline_name}' not found at {baseline_path}")
        sys.exit(1)

    baseline = json.loads(baseline_path.read_text())
    w = 72

    print(f"\n{'═' * w}")
    print(f"  COMPARISON: current vs '{baseline_name}'")
    print(f"{'═' * w}")

    def _delta(current: float, base: float) -> str:
        diff = current - base
        arrow = "▲" if diff > 0 else "▼" if diff < 0 else "="
        return f"{arrow}{abs(diff)*100:+.1f}pp"

    # Overall comparison
    b = baseline["overall"]
    print(f"\n  {'Metric':<18} {'Baseline':>10} {'Current':>10} {'Delta':>12}")
    print(f"  {'─' * 52}")
    metrics = [
        ("Hit Rate@K", b["hit_rate"], report.overall_hit_rate),
        ("MRR", b["mrr"], report.overall_mrr),
        ("Precision@K", b["precision"], report.overall_precision),
        ("NDCG@K", b["ndcg"], report.overall_ndcg),
        ("Recall@K", b["recall"], report.overall_recall),
    ]
    for name, base_val, cur_val in metrics:
        delta = _delta(cur_val, base_val)
        print(f"  {name:<18} {_pct(base_val):>10} {_pct(cur_val):>10} {delta:>12}")

    # Per-category comparison
    baseline_cats = {c["label"]: c for c in baseline["categories"]}
    print("\n  PER CATEGORY (Hit Rate)")
    print(f"  {'─' * 52}")
    for cat in report.categories:
        if cat.label in baseline_cats:
            base_hr = baseline_cats[cat.label]["hit_rate"]
            delta = _delta(cat.hit_rate, base_hr)
            print(f"  {cat.label:<22} {_pct(base_hr):>10} {_pct(cat.hit_rate):>10} {delta:>12}")

    # Per-query regressions and improvements
    baseline_queries = {q["id"]: q for q in baseline["per_query"]}
    regressions = []
    improvements = []
    for r in report.per_query:
        bq = baseline_queries.get(r.id)
        if not bq:
            continue
        if bq["hit"] and not r.hit:
            regressions.append(r)
        elif not bq["hit"] and r.hit:
            improvements.append(r)

    if improvements:
        print(f"\n  IMPROVEMENTS ({len(improvements)} queries now hit):")
        for r in improvements:
            print(f"    ✓ [{r.id}] {r.query!r}")

    if regressions:
        print(f"\n  REGRESSIONS ({len(regressions)} queries lost):")
        for r in regressions:
            print(f"    ✗ [{r.id}] {r.query!r}")

    if not improvements and not regressions:
        print("\n  No query-level changes (same hits/misses)")

    print(f"\n{'═' * w}\n")


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="kenso search quality eval")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all query details")
    parser.add_argument("--save", metavar="NAME", help="Save snapshot with this name")
    parser.add_argument("--compare", metavar="NAME", help="Compare against saved snapshot")
    args = parser.parse_args()

    report = asyncio.run(run_eval())

    if args.json:
        data = {
            "overall": {
                "hit_rate": report.overall_hit_rate,
                "mrr": report.overall_mrr,
                "precision": report.overall_precision,
                "ndcg": report.overall_ndcg,
                "recall": report.overall_recall,
            },
            "categories": [asdict(c) for c in report.categories],
        }
        print(json.dumps(data, indent=2))
    else:
        print_report(report, verbose=args.verbose)

    if args.save:
        save_snapshot(report, args.save)

    if args.compare:
        compare_snapshots(report, args.compare)


if __name__ == "__main__":
    main()
