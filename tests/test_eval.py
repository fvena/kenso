"""Integration test that runs the eval harness and checks minimum metrics."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add eval directory to path so corpus module can be imported
sys.path.insert(0, str(Path(__file__).parent / "eval"))

from eval_harness import run_eval  # noqa: E402


@pytest.fixture(scope="module")
async def eval_report():
    """Run the eval harness once and cache the report."""
    return await run_eval()


class TestEvalMinimumMetrics:
    async def test_hit_rate_above_threshold(self, eval_report):
        assert eval_report.overall_hit_rate >= 0.6, (
            f"Hit rate {eval_report.overall_hit_rate:.2%} below 60% minimum"
        )

    async def test_mrr_above_threshold(self, eval_report):
        assert eval_report.overall_mrr >= 0.4, (
            f"MRR {eval_report.overall_mrr:.2%} below 40% minimum"
        )

    async def test_precision_above_threshold(self, eval_report):
        assert eval_report.overall_precision >= 0.2, (
            f"Precision {eval_report.overall_precision:.2%} below 20% minimum"
        )

    async def test_has_queries(self, eval_report):
        assert eval_report.total_queries > 0

    async def test_has_categories(self, eval_report):
        assert len(eval_report.categories) > 0


class TestEvalFeatureTests:
    async def test_typed_relations_stored(self, eval_report):
        assert eval_report.feature_tests.get("typed_relations_stored", {}).get("pass"), (
            "Typed relations should be stored correctly"
        )

    async def test_depth_traversal(self, eval_report):
        assert eval_report.feature_tests.get("depth_1_direct", {}).get("pass"), (
            "Depth-1 traversal should find direct neighbors"
        )

    async def test_depth_2_expands(self, eval_report):
        assert eval_report.feature_tests.get("depth_2_expands", {}).get("pass"), (
            "Depth-2 should discover more neighbors than depth-1"
        )

    async def test_relation_type_filter(self, eval_report):
        assert eval_report.feature_tests.get("relation_type_filter", {}).get("pass"), (
            "Relation type filter should narrow results"
        )
