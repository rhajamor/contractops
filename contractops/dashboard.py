"""Dashboard analytics: trend analysis, risk scoring, and executive KPIs.

Provides the data layer for the enterprise control plane. Consumes audit
logs and suite results to compute drift hotspots, reliability trends,
policy coverage metrics, and per-scenario risk analysis.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any

from contractops.audit import AuditLog
from contractops.models import SuiteResult

logger = logging.getLogger("contractops.dashboard")


class DashboardAnalytics:
    """Computes enterprise KPIs and trend data from audit logs and suite results."""

    def __init__(self, audit_log: AuditLog) -> None:
        self._audit = audit_log

    def executive_summary(self) -> dict[str, Any]:
        """High-level KPIs for leadership dashboards."""
        events = self._audit.get_events(event_type="gate_decision")
        if not events:
            return {
                "total_gates": 0,
                "pass_rate": 0.0,
                "mean_score": 0.0,
                "incidents_prevented": 0,
                "gate_bypass_rate": 0.0,
            }

        total = len(events)
        passed = sum(1 for e in events if e.get("details", {}).get("passed"))
        failed = total - passed
        scores = [
            e.get("details", {}).get("score", 0) for e in events
        ]
        mean_score = sum(scores) / total if total else 0.0

        return {
            "total_gates": total,
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "mean_score": round(mean_score, 2),
            "incidents_prevented": failed,
            "gate_bypass_rate": 0.0,
        }

    def scenario_risk_scores(self) -> list[dict[str, Any]]:
        """Per-scenario risk analysis based on historical gate results."""
        events = self._audit.get_events(event_type="gate_decision")
        scenario_data: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for event in events:
            sid = event.get("scenario_id", "")
            if sid:
                scenario_data[sid].append(event.get("details", {}))

        results: list[dict[str, Any]] = []
        for sid, runs in sorted(scenario_data.items()):
            total = len(runs)
            failures = sum(1 for r in runs if not r.get("passed"))
            scores = [r.get("score", 0) for r in runs]
            mean_score = sum(scores) / total if total else 0
            score_var = (
                sum((s - mean_score) ** 2 for s in scores) / total
                if total > 1 else 0.0
            )

            failure_rate = failures / total if total else 0
            variance_penalty = min(math.sqrt(score_var) / 20, 10)
            risk_score = round(
                failure_rate * 60 + (1 - mean_score / 100) * 30 + variance_penalty, 2
            )

            results.append({
                "scenario_id": sid,
                "total_runs": total,
                "failure_count": failures,
                "failure_rate": round(failure_rate, 4),
                "mean_score": round(mean_score, 2),
                "score_variance": round(score_var, 4),
                "risk_score": min(risk_score, 100.0),
            })

        return sorted(results, key=lambda r: -r["risk_score"])

    def drift_hotspots(self, threshold: float = 0.8) -> list[dict[str, Any]]:
        """Identify scenarios with frequent drift (low similarity)."""
        events = self._audit.get_events(event_type="gate_decision")
        scenario_sims: dict[str, list[float]] = defaultdict(list)

        for event in events:
            details = event.get("details", {})
            sid = event.get("scenario_id", "")
            reasons = details.get("reasons", [])
            for reason in reasons:
                if "similarity" in reason.lower():
                    scenario_sims[sid].append(0.0)
                    break
            else:
                scenario_sims[sid].append(1.0)

        hotspots: list[dict[str, Any]] = []
        for sid, sims in sorted(scenario_sims.items()):
            drift_rate = sum(1 for s in sims if s < threshold) / len(sims) if sims else 0
            if drift_rate > 0:
                hotspots.append({
                    "scenario_id": sid,
                    "drift_rate": round(drift_rate, 4),
                    "total_checks": len(sims),
                })

        return sorted(hotspots, key=lambda h: -h["drift_rate"])

    def reliability_trend(self, window_size: int = 10) -> list[dict[str, Any]]:
        """Compute rolling pass rate and score over time windows."""
        events = self._audit.get_events(event_type="gate_decision")
        if not events:
            return []

        trend: list[dict[str, Any]] = []
        for i in range(0, len(events), max(1, window_size)):
            window = events[i:i + window_size]
            passed = sum(1 for e in window if e.get("details", {}).get("passed"))
            scores = [e.get("details", {}).get("score", 0) for e in window]
            trend.append({
                "window_start": window[0].get("timestamp", ""),
                "window_end": window[-1].get("timestamp", ""),
                "events": len(window),
                "pass_rate": round(passed / len(window), 4),
                "mean_score": round(sum(scores) / len(scores), 2) if scores else 0,
            })

        return trend

    def policy_coverage(self) -> dict[str, Any]:
        """Assess how well scenarios cover different policy domains."""
        events = self._audit.get_events(event_type="gate_decision")
        unique_scenarios = set(e.get("scenario_id", "") for e in events)

        return {
            "unique_scenarios_tested": len(unique_scenarios),
            "total_gate_runs": len(events),
            "scenarios": sorted(unique_scenarios),
        }


def compute_suite_kpis(suite: SuiteResult) -> dict[str, Any]:
    """Extract dashboard-ready KPIs from a single suite run."""
    latencies = [s.latency_ms for s in suite.scenarios]
    scores = [s.score for s in suite.scenarios]

    return {
        "passed": suite.passed,
        "total": suite.total,
        "pass_rate": round(suite.pass_rate, 4),
        "mean_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "p50_latency_ms": sorted(latencies)[len(latencies) // 2] if latencies else 0,
        "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
        "max_latency_ms": max(latencies) if latencies else 0,
        "flaky_count": suite.flaky_count,
        "failed_scenarios": [s.scenario_id for s in suite.failed_scenarios()],
    }
