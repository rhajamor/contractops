"""Tests for multi-trial stability and confidence-aware reporting."""

from __future__ import annotations

from pathlib import Path

from contractops.baseline import save_baseline
from contractops.executors import MockExecutor
from contractops.models import Scenario, StabilityMetrics
from contractops.report import render_suite_markdown
from contractops.storage import LocalStorage
from contractops.suite import run_suite


def _make_scenarios(count: int = 3) -> list[Scenario]:
    return [
        Scenario(
            id=f"stability-{i}",
            description=f"Stability test {i}",
            input="I need help with refund." if i % 2 == 0 else "Hello, help me.",
            expected={"must_include": ["next steps"]},
        )
        for i in range(count)
    ]


class TestMultiTrialSuite:
    def test_single_trial_no_stability(self) -> None:
        scenarios = _make_scenarios(2)
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, trials=1, min_score=0, min_similarity=0.0)
        assert result.passed
        for s in result.scenarios:
            assert s.stability is None

    def test_multi_trial_produces_stability(self) -> None:
        scenarios = _make_scenarios(1)
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, trials=3, min_score=0, min_similarity=0.0)
        assert result.total == 1
        report = result.scenarios[0]
        assert report.stability is not None
        assert isinstance(report.stability, StabilityMetrics)
        assert report.stability.trials_run == 3

    def test_deterministic_executor_stable(self) -> None:
        scenarios = _make_scenarios(1)
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, trials=5, min_score=0, min_similarity=0.0)
        report = result.scenarios[0]
        assert report.stability is not None
        assert report.stability.trials_passed == 5
        assert report.stability.pass_rate == 1.0
        assert not report.stability.is_flaky
        assert report.stability.score_variance == 0.0

    def test_pass_threshold_enforcement(self) -> None:
        scenarios = [
            Scenario(
                id="flaky-test",
                description="Intentionally flaky",
                input="help me",
                expected={"must_include": ["nonexistent_phrase_xyz"]},
            )
        ]
        executor = MockExecutor("v1")
        result = run_suite(
            scenarios, executor, trials=3, pass_threshold=0.8,
            min_score=0, min_similarity=0.0,
        )
        report = result.scenarios[0]
        assert not report.passed
        assert report.stability is not None
        assert report.stability.trials_passed == 0

    def test_multi_trial_with_baselines(self, tmp_dir: Path) -> None:
        storage = LocalStorage(str(tmp_dir / "baselines"))
        scenarios = [
            Scenario(
                id="s-stable",
                description="Stable with baseline",
                input="help me",
                expected={"must_include": ["help"]},
            )
        ]
        executor = MockExecutor("v1")
        baseline_result = executor.run(scenarios[0])
        save_baseline(baseline_result, storage=storage)

        result = run_suite(
            scenarios, executor, storage=storage, trials=3,
            min_similarity=0.0, min_score=0,
        )
        assert result.passed
        report = result.scenarios[0]
        assert report.stability is not None
        assert report.stability.trials_passed == 3
        assert report.similarity is not None

    def test_stability_metrics_math(self) -> None:
        scenarios = _make_scenarios(2)
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, trials=4, min_score=0, min_similarity=0.0)
        for report in result.scenarios:
            assert report.stability is not None
            stab = report.stability
            assert stab.mean_score >= 0
            assert stab.score_stddev >= 0
            assert stab.mean_latency_ms >= 0


class TestStabilityReporting:
    def test_markdown_includes_stability_columns(self) -> None:
        scenarios = _make_scenarios(2)
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, trials=3, min_score=0, min_similarity=0.0)
        md = render_suite_markdown(result, min_similarity=0.85, min_score=80)
        assert "Trials" in md
        assert "Stability" in md
        assert "STABLE" in md

    def test_markdown_no_stability_for_single_trial(self) -> None:
        scenarios = _make_scenarios(2)
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, trials=1, min_score=0, min_similarity=0.0)
        md = render_suite_markdown(result, min_similarity=0.85, min_score=80)
        assert "Trials" not in md

    def test_flaky_count_in_suite(self) -> None:
        scenarios = _make_scenarios(2)
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, trials=3, min_score=0, min_similarity=0.0)
        assert result.flaky_count == 0


class TestSemanticBaseline:
    """Test semantic similarity in baseline comparison (live Ollama)."""

    def test_semantic_comparison(self, tmp_dir: Path) -> None:
        storage = LocalStorage(str(tmp_dir / "baselines"))
        scenarios = [
            Scenario(
                id="sem-test",
                description="Semantic baseline test",
                input="I need help with refund.",
                expected={"must_include": ["refund"]},
            )
        ]
        executor = MockExecutor("v1")
        baseline_result = executor.run(scenarios[0])
        save_baseline(baseline_result, storage=storage)

        result = run_suite(
            scenarios, executor, storage=storage,
            use_semantic=True, embed_model="llama3.1:8b",
            min_similarity=0.0, min_score=0,
        )
        assert result.passed
        report = result.scenarios[0]
        assert report.similarity is not None
        assert report.similarity > 0.9
