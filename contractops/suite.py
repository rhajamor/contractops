"""Suite runner: batch execution of multiple scenarios with aggregated reporting."""

from __future__ import annotations

import concurrent.futures
import logging
from typing import Any

from contractops.assertions import evaluate_contracts
from contractops.baseline import baseline_exists, compare_outputs, load_baseline
from contractops.executors import Executor
from contractops.models import Scenario, ScenarioReport, SuiteResult
from contractops.report import build_release_report
from contractops.storage import BaselineStorage

logger = logging.getLogger("contractops.suite")


def run_suite(
    scenarios: list[Scenario],
    executor: Executor,
    storage: BaselineStorage | None = None,
    min_similarity: float = 0.85,
    min_score: int = 80,
    require_baseline: bool = False,
    parallel: int = 1,
) -> SuiteResult:
    """Execute all scenarios and return an aggregated SuiteResult."""
    if parallel > 1:
        reports = _run_parallel(
            scenarios, executor, storage, min_similarity, min_score, require_baseline, parallel,
        )
    else:
        reports = [
            _run_single(s, executor, storage, min_similarity, min_score, require_baseline)
            for s in scenarios
        ]

    passed_count = sum(1 for r in reports if r.passed)
    failed_count = len(reports) - passed_count
    total = len(reports)
    avg_score = sum(r.score for r in reports) / total if total else 0

    return SuiteResult(
        passed=failed_count == 0,
        total=total,
        passed_count=passed_count,
        failed_count=failed_count,
        score=round(avg_score, 2),
        scenarios=reports,
    )


def _run_single(
    scenario: Scenario,
    executor: Executor,
    storage: BaselineStorage | None,
    min_similarity: float,
    min_score: int,
    require_baseline: bool,
) -> ScenarioReport:
    try:
        result = executor.run(scenario)
        contract_eval = evaluate_contracts(scenario, result)

        baseline_comparison = _load_baseline_comparison(
            scenario.id, result.output, storage
        )

        if require_baseline and baseline_comparison is None:
            return ScenarioReport(
                scenario_id=scenario.id,
                passed=False,
                score=0,
                contract_pass_rate=contract_eval.pass_rate,
                similarity=None,
                latency_ms=result.latency_ms,
                executor=result.executor,
                reasons=[f"Baseline not found for scenario '{scenario.id}'."],
                checks=[
                    {"name": c.name, "passed": c.passed, "detail": c.detail}
                    for c in contract_eval.checks
                ],
                candidate_output=result.output,
                diff_preview=[],
                diff_truncated=False,
                tool_calls=result.tool_calls,
            )

        report = build_release_report(
            scenario=scenario,
            run_result=result,
            contract_eval=contract_eval,
            baseline_comparison=baseline_comparison,
            min_similarity=min_similarity,
            min_score=min_score,
        )
        return _report_to_scenario_report(report)

    except Exception as exc:
        logger.error("Scenario '%s' failed: %s", scenario.id, exc)
        return ScenarioReport(
            scenario_id=scenario.id,
            passed=False,
            score=0,
            contract_pass_rate=0.0,
            similarity=None,
            latency_ms=0,
            executor=executor.name,
            reasons=[f"Execution error: {exc}"],
            checks=[],
            candidate_output="",
            diff_preview=[],
            diff_truncated=False,
            tool_calls=[],
        )


def _run_parallel(
    scenarios: list[Scenario],
    executor: Executor,
    storage: BaselineStorage | None,
    min_similarity: float,
    min_score: int,
    require_baseline: bool,
    max_workers: int,
) -> list[ScenarioReport]:
    reports: list[ScenarioReport] = [None] * len(scenarios)  # type: ignore[list-item]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(
                _run_single, s, executor, storage, min_similarity, min_score, require_baseline
            ): idx
            for idx, s in enumerate(scenarios)
        }
        for future in concurrent.futures.as_completed(future_map):
            idx = future_map[future]
            reports[idx] = future.result()
    return reports


def _load_baseline_comparison(
    scenario_id: str,
    candidate_output: str,
    storage: BaselineStorage | None,
) -> dict[str, Any] | None:
    if storage is None:
        return None
    if not baseline_exists(scenario_id=scenario_id, storage=storage):
        return None
    try:
        payload = load_baseline(scenario_id=scenario_id, storage=storage)
        baseline_output = str(payload["run_result"]["output"])
        return compare_outputs(baseline_output, candidate_output)
    except (FileNotFoundError, KeyError):
        return None


def _report_to_scenario_report(report: dict[str, Any]) -> ScenarioReport:
    return ScenarioReport(
        scenario_id=report["scenario_id"],
        passed=report["passed"],
        score=report["score"],
        contract_pass_rate=report["contract_pass_rate"],
        similarity=report["similarity"],
        latency_ms=report["latency_ms"],
        executor=report["executor"],
        reasons=report["reasons"],
        checks=report["checks"],
        candidate_output=report["candidate_output"],
        diff_preview=report["diff_preview"],
        diff_truncated=report["diff_truncated"],
        tool_calls=report["tool_calls"],
    )
