from pathlib import Path

from contractops.baseline import save_baseline
from contractops.executors import MockExecutor
from contractops.models import Scenario
from contractops.storage import LocalStorage
from contractops.suite import run_suite


def _make_scenarios(count: int = 3) -> list[Scenario]:
    return [
        Scenario(
            id=f"scenario-{i}",
            description=f"Test {i}",
            input="I need help with refund." if i % 2 == 0 else "Hello, help me.",
            expected={"must_include": ["next steps"]},
        )
        for i in range(count)
    ]


class TestRunSuite:
    def test_all_pass(self):
        scenarios = _make_scenarios(3)
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, min_score=0, min_similarity=0.0)
        assert result.passed
        assert result.total == 3
        assert result.passed_count == 3
        assert result.failed_count == 0

    def test_some_fail(self):
        scenarios = [
            Scenario(
                id="pass", description="d", input="help me",
                expected={"must_include": ["help"]},
            ),
            Scenario(
                id="fail", description="d", input="help me",
                expected={"must_include": ["nonexistent_phrase_xyz"]},
            ),
        ]
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, min_score=0, min_similarity=0.0)
        assert not result.passed
        assert result.passed_count == 1
        assert result.failed_count == 1

    def test_with_baselines(self, tmp_dir: Path):
        storage = LocalStorage(str(tmp_dir / "baselines"))
        scenarios = [
            Scenario(
                id="s1", description="d", input="help me",
                expected={"must_include": ["help"]},
            ),
        ]
        executor = MockExecutor("v1")

        baseline_result = executor.run(scenarios[0])
        save_baseline(baseline_result, storage=storage)

        result = run_suite(
            scenarios, executor, storage=storage,
            min_similarity=0.0, min_score=0,
        )
        assert result.passed
        assert result.scenarios[0].similarity is not None
        assert result.scenarios[0].similarity == 1.0

    def test_require_baseline_fails_when_missing(self, tmp_dir: Path):
        storage = LocalStorage(str(tmp_dir / "baselines"))
        scenarios = _make_scenarios(1)
        executor = MockExecutor("v1")
        result = run_suite(
            scenarios, executor, storage=storage,
            require_baseline=True,
        )
        assert not result.passed
        assert "Baseline not found" in result.scenarios[0].reasons[0]

    def test_parallel(self):
        scenarios = _make_scenarios(6)
        executor = MockExecutor("v1")
        result = run_suite(
            scenarios, executor, parallel=3, min_score=0, min_similarity=0.0,
        )
        assert result.total == 6
        assert result.passed

    def test_empty_suite(self):
        executor = MockExecutor("v1")
        result = run_suite([], executor)
        assert result.passed
        assert result.total == 0
