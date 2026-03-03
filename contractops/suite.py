"""Suite runner: batch execution with multi-trial stability and aggregated reporting."""

from __future__ import annotations

import concurrent.futures
import logging
import math
from typing import Any

from contractops.assertions import evaluate_contracts
from contractops.baseline import baseline_exists, compare_outputs, load_baseline
from contractops.executors import Executor
from contractops.models import (
    Scenario,
    ScenarioReport,
    StabilityMetrics,
    SuiteResult,
    TrialResult,
)
from contractops.report import build_release_report
from contractops.storage import BaselineStorage

logger = logging.getLogger("contractops.suite")

_FLAKY_THRESHOLD = 0.2  # pass rate variance that triggers flaky warning


def run_suite(
    scenarios: list[Scenario],
    executor: Executor,
    storage: BaselineStorage | None = None,
    min_similarity: float = 0.85,
    min_score: int = 80,
    require_baseline: bool = False,
    parallel: int = 1,
    trials: int = 1,
    pass_threshold: float = 1.0,
    use_semantic: bool = False,
    embed_model: str = "",
    embed_url: str = "",
) -> SuiteResult:
    """Execute all scenarios and return an aggregated SuiteResult.

    When *trials* > 1, each scenario is executed multiple times and stability
    metrics (mean, variance, flaky detection) are computed. A scenario passes
    only if its trial pass rate meets *pass_threshold* (default 100%).
    """
    run_kwargs = {
        "storage": storage,
        "min_similarity": min_similarity,
        "min_score": min_score,
        "require_baseline": require_baseline,
        "trials": trials,
        "pass_threshold": pass_threshold,
        "use_semantic": use_semantic,
        "embed_model": embed_model,
        "embed_url": embed_url,
    }

    if parallel > 1:
        reports = _run_parallel(scenarios, executor, run_kwargs, parallel)
    else:
        reports = [
            _run_single(s, executor, **run_kwargs)
            for s in scenarios
        ]

    passed_count = sum(1 for r in reports if r.passed)
    failed_count = len(reports) - passed_count
    total = len(reports)
    avg_score = sum(r.score for r in reports) / total if total else 0
    flaky_count = sum(
        1 for r in reports
        if r.stability is not None and r.stability.is_flaky
    )

    return SuiteResult(
        passed=failed_count == 0,
        total=total,
        passed_count=passed_count,
        failed_count=failed_count,
        score=round(avg_score, 2),
        scenarios=reports,
        flaky_count=flaky_count,
    )


def _run_single(
    scenario: Scenario,
    executor: Executor,
    storage: BaselineStorage | None = None,
    min_similarity: float = 0.85,
    min_score: int = 80,
    require_baseline: bool = False,
    trials: int = 1,
    pass_threshold: float = 1.0,
    use_semantic: bool = False,
    embed_model: str = "",
    embed_url: str = "",
) -> ScenarioReport:
    if trials > 1:
        return _run_with_trials(
            scenario, executor, storage, min_similarity, min_score,
            require_baseline, trials, pass_threshold, use_semantic,
            embed_model, embed_url,
        )
    return _run_once(
        scenario, executor, storage, min_similarity, min_score,
        require_baseline, use_semantic, embed_model, embed_url,
    )


def _run_once(
    scenario: Scenario,
    executor: Executor,
    storage: BaselineStorage | None,
    min_similarity: float,
    min_score: int,
    require_baseline: bool,
    use_semantic: bool = False,
    embed_model: str = "",
    embed_url: str = "",
) -> ScenarioReport:
    try:
        result = executor.run(scenario)
        contract_eval = evaluate_contracts(scenario, result)

        baseline_comparison = _load_baseline_comparison(
            scenario.id, result.output, storage,
            use_semantic=use_semantic, embed_model=embed_model, embed_url=embed_url,
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


def _run_with_trials(
    scenario: Scenario,
    executor: Executor,
    storage: BaselineStorage | None,
    min_similarity: float,
    min_score: int,
    require_baseline: bool,
    trials: int,
    pass_threshold: float,
    use_semantic: bool,
    embed_model: str,
    embed_url: str,
) -> ScenarioReport:
    """Run a scenario multiple times and compute stability metrics."""
    trial_results: list[TrialResult] = []
    reports: list[ScenarioReport] = []

    for i in range(trials):
        report = _run_once(
            scenario, executor, storage, min_similarity, min_score,
            require_baseline, use_semantic, embed_model, embed_url,
        )
        reports.append(report)
        trial_results.append(TrialResult(
            trial_index=i,
            passed=report.passed,
            score=report.score,
            contract_pass_rate=report.contract_pass_rate,
            similarity=report.similarity,
            latency_ms=report.latency_ms,
            output=report.candidate_output,
        ))

    stability = _compute_stability(trial_results)

    best = max(reports, key=lambda r: r.score)
    trial_pass_rate = stability.pass_rate
    overall_passed = trial_pass_rate >= pass_threshold and best.passed

    reasons = list(best.reasons)
    if stability.is_flaky:
        reasons.append(f"FLAKY: {stability.flaky_reason}")
    if trial_pass_rate < pass_threshold:
        reasons.append(
            f"Trial pass rate {trial_pass_rate:.0%} below threshold {pass_threshold:.0%} "
            f"({stability.trials_passed}/{stability.trials_run} trials passed)."
        )

    return ScenarioReport(
        scenario_id=best.scenario_id,
        passed=overall_passed,
        score=int(round(stability.mean_score)),
        contract_pass_rate=best.contract_pass_rate,
        similarity=best.similarity,
        latency_ms=int(round(stability.mean_latency_ms)),
        executor=best.executor,
        reasons=reasons,
        checks=best.checks,
        candidate_output=best.candidate_output,
        diff_preview=best.diff_preview,
        diff_truncated=best.diff_truncated,
        tool_calls=best.tool_calls,
        stability=stability,
    )


def _compute_stability(trial_results: list[TrialResult]) -> StabilityMetrics:
    n = len(trial_results)
    if n == 0:
        return StabilityMetrics(
            trials_run=0, trials_passed=0, pass_rate=0.0,
            mean_score=0.0, score_variance=0.0, score_stddev=0.0,
            mean_latency_ms=0.0, latency_variance=0.0,
            is_flaky=False, flaky_reason="",
            trial_results=trial_results,
        )

    scores = [t.score for t in trial_results]
    latencies = [float(t.latency_ms) for t in trial_results]
    passed_count = sum(1 for t in trial_results if t.passed)
    pass_rate = passed_count / n

    mean_score = sum(scores) / n
    score_var = sum((s - mean_score) ** 2 for s in scores) / n if n > 1 else 0.0
    score_std = math.sqrt(score_var)

    mean_lat = sum(latencies) / n
    lat_var = sum((lat - mean_lat) ** 2 for lat in latencies) / n if n > 1 else 0.0

    is_flaky = False
    flaky_reason = ""
    if 0 < pass_rate < 1.0:
        is_flaky = True
        flaky_reason = (
            f"Inconsistent results: {passed_count}/{n} trials passed "
            f"(score stddev {score_std:.1f})."
        )
    elif score_std > _FLAKY_THRESHOLD * mean_score and mean_score > 0:
        is_flaky = True
        flaky_reason = f"High score variance: stddev {score_std:.1f} on mean {mean_score:.1f}."

    return StabilityMetrics(
        trials_run=n,
        trials_passed=passed_count,
        pass_rate=round(pass_rate, 4),
        mean_score=round(mean_score, 2),
        score_variance=round(score_var, 4),
        score_stddev=round(score_std, 4),
        mean_latency_ms=round(mean_lat, 2),
        latency_variance=round(lat_var, 4),
        is_flaky=is_flaky,
        flaky_reason=flaky_reason,
        trial_results=trial_results,
    )


def _run_parallel(
    scenarios: list[Scenario],
    executor: Executor,
    run_kwargs: dict[str, Any],
    max_workers: int,
) -> list[ScenarioReport]:
    reports: list[ScenarioReport] = [None] * len(scenarios)  # type: ignore[list-item]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(_run_single, s, executor, **run_kwargs): idx
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
    use_semantic: bool = False,
    embed_model: str = "",
    embed_url: str = "",
) -> dict[str, Any] | None:
    if storage is None:
        return None
    if not baseline_exists(scenario_id=scenario_id, storage=storage):
        return None
    try:
        payload = load_baseline(scenario_id=scenario_id, storage=storage)
        baseline_output = str(payload["run_result"]["output"])
        return compare_outputs(
            baseline_output, candidate_output,
            use_semantic=use_semantic,
            embed_model=embed_model,
            embed_url=embed_url,
        )
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
