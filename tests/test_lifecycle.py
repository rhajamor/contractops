"""Tests for baseline lifecycle management."""

from __future__ import annotations

from pathlib import Path

from contractops.baseline import save_baseline
from contractops.lifecycle import BaselineLifecycle, compare_baselines
from contractops.models import RunResult
from contractops.storage import LocalStorage


class TestBaselineLifecycle:
    def _make_lifecycle(self, tmp_dir: Path) -> BaselineLifecycle:
        storage = LocalStorage(str(tmp_dir / "baselines"))
        return BaselineLifecycle(storage)

    def test_initial_state_is_draft(self, tmp_dir: Path) -> None:
        lc = self._make_lifecycle(tmp_dir)
        state = lc.get_state("test-scenario")
        assert state["state"] == "draft"
        assert state["version"] == 0

    def test_approve_changes_state(self, tmp_dir: Path) -> None:
        lc = self._make_lifecycle(tmp_dir)
        meta = lc.approve("test-scenario", approver="admin")
        assert meta["state"] == "approved"
        assert meta["version"] == 1
        assert meta["approved_by"] == "admin"
        assert meta["approved_at"] is not None

    def test_double_approve_increments_version(self, tmp_dir: Path) -> None:
        lc = self._make_lifecycle(tmp_dir)
        lc.approve("test-scenario", approver="admin")
        meta = lc.approve("test-scenario", approver="manager")
        assert meta["version"] == 2
        assert meta["approved_by"] == "manager"
        assert len(meta["history"]) >= 1

    def test_expire_changes_state(self, tmp_dir: Path) -> None:
        lc = self._make_lifecycle(tmp_dir)
        lc.approve("test-scenario", approver="admin")
        meta = lc.expire("test-scenario", reason="Model upgrade")
        assert meta["state"] == "expired"
        assert meta["expire_reason"] == "Model upgrade"
        assert meta["expired_at"] is not None

    def test_rotate_increments_version(self, tmp_dir: Path) -> None:
        lc = self._make_lifecycle(tmp_dir)
        lc.approve("test-scenario", approver="admin")
        meta = lc.rotate("test-scenario", approver="deployer")
        assert meta["state"] == "approved"
        assert meta["version"] >= 2

    def test_is_approved(self, tmp_dir: Path) -> None:
        lc = self._make_lifecycle(tmp_dir)
        assert not lc.is_approved("test-scenario")
        lc.approve("test-scenario", approver="admin")
        assert lc.is_approved("test-scenario")
        lc.expire("test-scenario")
        assert not lc.is_approved("test-scenario")

    def test_version_history(self, tmp_dir: Path) -> None:
        lc = self._make_lifecycle(tmp_dir)
        lc.approve("test-scenario", approver="v1-approver")
        lc.approve("test-scenario", approver="v2-approver")
        lc.expire("test-scenario", reason="outdated")

        history = lc.list_versions("test-scenario")
        assert len(history) >= 2

    def test_empty_history(self, tmp_dir: Path) -> None:
        lc = self._make_lifecycle(tmp_dir)
        history = lc.list_versions("never-existed")
        assert history == []

    def test_multiple_scenarios_independent(self, tmp_dir: Path) -> None:
        lc = self._make_lifecycle(tmp_dir)
        lc.approve("scenario-a", approver="admin")
        lc.expire("scenario-b", reason="test")

        assert lc.is_approved("scenario-a")
        assert not lc.is_approved("scenario-b")
        assert lc.get_state("scenario-a")["state"] == "approved"
        assert lc.get_state("scenario-b")["state"] == "expired"


class TestCompareBaselines:
    def test_returns_none_when_no_baseline(self, tmp_dir: Path) -> None:
        storage = LocalStorage(str(tmp_dir / "baselines"))
        result = compare_baselines(storage, "nonexistent")
        assert result is None

    def test_returns_data_when_baseline_exists(self, tmp_dir: Path) -> None:
        storage = LocalStorage(str(tmp_dir / "baselines"))
        run_result = RunResult(
            scenario_id="test-compare",
            executor="mock-v1",
            output="Test output",
            latency_ms=100,
        )
        save_baseline(run_result, storage=storage)

        result = compare_baselines(storage, "test-compare")
        assert result is not None
        assert result["has_baseline"] is True
        assert result["lifecycle_state"] == "draft"
        assert result["executor"] == "mock-v1"

    def test_shows_approved_state(self, tmp_dir: Path) -> None:
        storage = LocalStorage(str(tmp_dir / "baselines"))
        run_result = RunResult(
            scenario_id="approved-scenario",
            executor="mock-v1",
            output="Approved output",
            latency_ms=50,
        )
        save_baseline(run_result, storage=storage)

        lc = BaselineLifecycle(storage)
        lc.approve("approved-scenario", approver="tester")

        result = compare_baselines(storage, "approved-scenario")
        assert result is not None
        assert result["lifecycle_state"] == "approved"
        assert result["version"] == 1
