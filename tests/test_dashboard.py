"""Tests for dashboard analytics and KPI computation."""

from __future__ import annotations

from pathlib import Path

from contractops.audit import AuditLog
from contractops.dashboard import DashboardAnalytics, compute_suite_kpis
from contractops.models import ScenarioReport, SuiteResult


def _make_suite(passed: bool = True, score: float = 90.0) -> SuiteResult:
    return SuiteResult(
        passed=passed,
        total=2,
        passed_count=2 if passed else 1,
        failed_count=0 if passed else 1,
        score=score,
        scenarios=[
            ScenarioReport(
                scenario_id="s1", passed=True, score=int(score),
                contract_pass_rate=1.0, similarity=0.95, latency_ms=100,
                executor="mock-v1", reasons=[], checks=[], candidate_output="",
                diff_preview=[], diff_truncated=False, tool_calls=[],
            ),
            ScenarioReport(
                scenario_id="s2", passed=passed,
                score=int(score - 20) if not passed else int(score),
                contract_pass_rate=0.5 if not passed else 1.0, similarity=0.8,
                latency_ms=200, executor="mock-v1",
                reasons=["Contract failed"] if not passed else [],
                checks=[], candidate_output="", diff_preview=[],
                diff_truncated=False, tool_calls=[],
            ),
        ],
    )


class TestDashboardAnalytics:
    def test_empty_executive_summary(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        analytics = DashboardAnalytics(log)
        summary = analytics.executive_summary()
        assert summary["total_gates"] == 0

    def test_executive_summary_with_data(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        log.record_gate_decision("s1", True, 90, "mock-v1", [])
        log.record_gate_decision("s2", False, 45, "mock-v2", ["Failed"])
        log.record_gate_decision("s3", True, 85, "mock-v1", [])

        analytics = DashboardAnalytics(log)
        summary = analytics.executive_summary()
        assert summary["total_gates"] == 3
        assert summary["incidents_prevented"] == 1
        assert summary["mean_score"] > 0

    def test_scenario_risk_scores(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        log.record_gate_decision("risky", False, 30, "v1", ["Failed"])
        log.record_gate_decision("risky", False, 40, "v1", ["Failed"])
        log.record_gate_decision("safe", True, 95, "v1", [])
        log.record_gate_decision("safe", True, 90, "v1", [])

        analytics = DashboardAnalytics(log)
        risks = analytics.scenario_risk_scores()
        assert len(risks) == 2
        assert risks[0]["scenario_id"] == "risky"
        assert risks[0]["failure_rate"] == 1.0

    def test_reliability_trend(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        for i in range(20):
            log.record_gate_decision(f"s{i}", i % 3 != 0, 80 + i, "v1", [])

        analytics = DashboardAnalytics(log)
        trend = analytics.reliability_trend(window_size=5)
        assert len(trend) >= 2
        for window in trend:
            assert "pass_rate" in window
            assert "mean_score" in window

    def test_policy_coverage(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        log.record_gate_decision("s1", True, 90, "v1", [])
        log.record_gate_decision("s2", True, 85, "v1", [])
        log.record_gate_decision("s1", True, 92, "v1", [])

        analytics = DashboardAnalytics(log)
        coverage = analytics.policy_coverage()
        assert coverage["unique_scenarios_tested"] == 2
        assert coverage["total_gate_runs"] == 3


class TestComputeSuiteKPIs:
    def test_passing_suite(self) -> None:
        kpis = compute_suite_kpis(_make_suite(passed=True))
        assert kpis["passed"]
        assert kpis["pass_rate"] == 1.0
        assert kpis["total"] == 2
        assert kpis["mean_score"] > 0
        assert kpis["p50_latency_ms"] > 0
        assert kpis["flaky_count"] == 0

    def test_failing_suite(self) -> None:
        kpis = compute_suite_kpis(_make_suite(passed=False))
        assert not kpis["passed"]
        assert kpis["pass_rate"] == 0.5
        assert len(kpis["failed_scenarios"]) == 1
