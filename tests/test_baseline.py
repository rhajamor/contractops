from pathlib import Path

import pytest

from contractops.baseline import (
    baseline_exists,
    baseline_key,
    compare_outputs,
    load_baseline,
    save_baseline,
)
from contractops.models import RunResult
from contractops.storage import LocalStorage


@pytest.fixture
def result() -> RunResult:
    return RunResult(
        scenario_id="test-scenario",
        executor="mock-v1",
        output="The refund was processed in 5 business days.",
        latency_ms=24,
        tool_calls=["tool.lookup_order"],
    )


class TestBaselineKey:
    def test_simple(self):
        assert baseline_key("my-scenario") == "my-scenario"

    def test_sanitizes_slashes(self):
        assert baseline_key("a/b\\c") == "a_b_c"


class TestSaveAndLoad:
    def test_save_and_load_with_storage(self, result, tmp_storage: LocalStorage):
        save_baseline(result, storage=tmp_storage)
        loaded = load_baseline(scenario_id="test-scenario", storage=tmp_storage)
        assert loaded["run_result"]["output"] == result.output
        assert loaded["run_result"]["scenario_id"] == "test-scenario"
        assert "saved_at" in loaded

    def test_save_and_load_with_path(self, result, tmp_dir: Path):
        path = tmp_dir / "bl.json"
        save_baseline(result, path=path)
        loaded = load_baseline(path=path)
        assert loaded["run_result"]["output"] == result.output

    def test_no_storage_or_path_raises(self, result):
        with pytest.raises(ValueError):
            save_baseline(result)

    def test_load_nonexistent(self, tmp_storage: LocalStorage):
        with pytest.raises(FileNotFoundError):
            load_baseline(scenario_id="missing", storage=tmp_storage)


class TestBaselineExists:
    def test_exists(self, result, tmp_storage: LocalStorage):
        save_baseline(result, storage=tmp_storage)
        assert baseline_exists(scenario_id="test-scenario", storage=tmp_storage)

    def test_not_exists(self, tmp_storage: LocalStorage):
        assert not baseline_exists(scenario_id="nope", storage=tmp_storage)

    def test_with_path(self, result, tmp_dir: Path):
        path = tmp_dir / "bl.json"
        assert not baseline_exists(path=path)
        save_baseline(result, path=path)
        assert baseline_exists(path=path)


class TestCompareOutputs:
    def test_identical(self):
        result = compare_outputs("hello world", "hello world")
        assert result["similarity"] == 1.0
        assert result["diff_preview"] == []

    def test_completely_different(self):
        result = compare_outputs("aaa", "zzz")
        assert result["similarity"] < 0.5

    def test_similar(self):
        baseline = "The refund will be processed in 5 business days."
        candidate = "The refund will be processed in 7 business days."
        result = compare_outputs(baseline, candidate)
        assert 0.8 < result["similarity"] < 1.0
        assert len(result["diff_preview"]) > 0

    def test_diff_truncation(self):
        baseline = "\n".join(f"line {i}" for i in range(50))
        candidate = "\n".join(f"changed {i}" for i in range(50))
        result = compare_outputs(baseline, candidate, max_diff_lines=5)
        assert result["diff_truncated"] is True
        assert len(result["diff_preview"]) == 5
