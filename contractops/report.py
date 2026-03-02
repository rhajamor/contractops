"""Release reporting: single-scenario and suite-level reports in multiple formats."""

from __future__ import annotations

from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from contractops.models import ContractEvaluation, RunResult, Scenario, SuiteResult


def build_release_report(
    scenario: Scenario,
    run_result: RunResult,
    contract_eval: ContractEvaluation,
    baseline_comparison: dict[str, Any] | None,
    min_similarity: float,
    min_score: int,
) -> dict[str, Any]:
    similarity = None
    if baseline_comparison is not None:
        similarity = float(baseline_comparison["similarity"])

    score = _score_release(contract_eval.pass_rate, similarity)

    reasons: list[str] = []
    if not contract_eval.passed:
        reasons.append("One or more hard contract checks failed.")
    if similarity is not None and similarity < min_similarity:
        reasons.append(
            f"Behavior drift is above threshold "
            f"(similarity {similarity:.3f} < {min_similarity:.3f})."
        )
    if score < min_score:
        reasons.append(f"Release score below threshold ({score} < {min_score}).")

    passed = len(reasons) == 0
    return {
        "passed": passed,
        "score": score,
        "scenario_id": scenario.id,
        "executor": run_result.executor,
        "latency_ms": run_result.latency_ms,
        "contract_pass_rate": round(contract_eval.pass_rate, 4),
        "similarity": similarity,
        "reasons": reasons,
        "checks": [
            {"name": c.name, "passed": c.passed, "detail": c.detail}
            for c in contract_eval.checks
        ],
        "candidate_output": run_result.output,
        "diff_preview": [] if baseline_comparison is None else baseline_comparison["diff_preview"],
        "diff_truncated": False
        if baseline_comparison is None
        else bool(baseline_comparison["diff_truncated"]),
        "tool_calls": run_result.tool_calls,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_markdown(report: dict[str, Any], min_similarity: float, min_score: int) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    similarity = report["similarity"]
    similarity_text = "n/a" if similarity is None else f"{similarity:.3f}"

    lines = [
        f"# ContractOps Result: {status}",
        "",
        f"- Scenario: `{report['scenario_id']}`",
        f"- Executor: `{report['executor']}`",
        f"- Release score: `{report['score']}` (threshold `{min_score}`)",
        f"- Contract pass rate: `{report['contract_pass_rate']:.2%}`",
        f"- Similarity to baseline: `{similarity_text}` (threshold `{min_similarity:.3f}`)",
        f"- Latency: `{report['latency_ms']} ms`",
        "",
        "## Contract Checks",
    ]

    for check in report["checks"]:
        prefix = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- [{prefix}] `{check['name']}` - {check['detail']}")

    lines.extend(["", "## Tool Calls"])
    if report["tool_calls"]:
        for tool in report["tool_calls"]:
            lines.append(f"- `{tool}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Candidate Output", report["candidate_output"]])

    if report["diff_preview"]:
        lines.extend(["", "## Baseline Diff Preview", "```diff"])
        lines.extend(report["diff_preview"])
        if report["diff_truncated"]:
            lines.append("... (diff truncated)")
        lines.append("```")

    if report["reasons"]:
        lines.extend(["", "## Decision Reasons"])
        for reason in report["reasons"]:
            lines.append(f"- {reason}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Suite-level markdown
# ---------------------------------------------------------------------------

def render_suite_markdown(suite: SuiteResult, min_similarity: float, min_score: int) -> str:
    status = "PASS" if suite.passed else "FAIL"
    lines = [
        f"# ContractOps Suite Result: {status}",
        "",
        f"- Total scenarios: `{suite.total}`",
        f"- Passed: `{suite.passed_count}`",
        f"- Failed: `{suite.failed_count}`",
        f"- Average score: `{suite.score:.1f}`",
        f"- Pass rate: `{suite.pass_rate:.0%}`",
        "",
    ]

    if suite.failed_scenarios():
        lines.append("## Failed Scenarios")
        lines.append("")
        for s in suite.failed_scenarios():
            lines.append(f"### `{s.scenario_id}` (score: {s.score})")
            for reason in s.reasons:
                lines.append(f"- {reason}")
            for check in s.checks:
                if not check["passed"]:
                    lines.append(f"  - [FAIL] `{check['name']}` - {check['detail']}")
            lines.append("")

    lines.append("## All Scenarios")
    lines.append("")
    lines.append("| Scenario | Status | Score | Contract Rate | Similarity | Latency |")
    lines.append("|----------|--------|-------|---------------|------------|---------|")
    for s in suite.scenarios:
        st = "PASS" if s.passed else "FAIL"
        sim = "n/a" if s.similarity is None else f"{s.similarity:.3f}"
        lines.append(
            f"| `{s.scenario_id}` | {st} | {s.score} | "
            f"{s.contract_pass_rate:.0%} | {sim} | {s.latency_ms}ms |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JUnit XML (for CI integration)
# ---------------------------------------------------------------------------

def render_junit_xml(suite: SuiteResult) -> str:
    """Render suite results as JUnit XML for CI tools like Jenkins, GitHub Actions."""
    root = Element("testsuites")
    root.set("name", "contractops")
    root.set("tests", str(suite.total))
    root.set("failures", str(suite.failed_count))
    root.set("errors", "0")

    ts = SubElement(root, "testsuite")
    ts.set("name", "contractops")
    ts.set("tests", str(suite.total))
    ts.set("failures", str(suite.failed_count))

    for scenario_report in suite.scenarios:
        tc = SubElement(ts, "testcase")
        tc.set("name", scenario_report.scenario_id)
        tc.set("classname", f"contractops.{scenario_report.executor}")
        tc.set("time", str(scenario_report.latency_ms / 1000.0))

        if not scenario_report.passed:
            failure = SubElement(tc, "failure")
            failure.set("message", "; ".join(scenario_report.reasons))
            failure_details: list[str] = []
            for check in scenario_report.checks:
                if not check["passed"]:
                    failure_details.append(f"[FAIL] {check['name']}: {check['detail']}")
            failure.text = "\n".join(failure_details)

    return tostring(root, encoding="unicode", xml_declaration=True)


# ---------------------------------------------------------------------------
# GitHub PR comment format
# ---------------------------------------------------------------------------

def render_github_comment(suite: SuiteResult, min_similarity: float, min_score: int) -> str:
    """Render suite results as a collapsible GitHub PR comment."""
    status_emoji = "white_check_mark" if suite.passed else "x"
    lines = [
        f"## ContractOps: :{status_emoji}: {'PASS' if suite.passed else 'FAIL'}",
        "",
        f"**{suite.passed_count}/{suite.total}** scenarios passed "
        f"| avg score **{suite.score:.0f}**",
        "",
    ]

    if suite.failed_scenarios():
        lines.append("### Failed Scenarios")
        lines.append("")
        for s in suite.failed_scenarios():
            lines.append(f"- **`{s.scenario_id}`** (score: {s.score})")
            for reason in s.reasons:
                lines.append(f"  - {reason}")
        lines.append("")

    lines.append("<details>")
    lines.append("<summary>Full results</summary>")
    lines.append("")
    lines.append("| Scenario | Status | Score | Similarity |")
    lines.append("|----------|--------|-------|------------|")
    for s in suite.scenarios:
        st = "PASS" if s.passed else "FAIL"
        sim = "n/a" if s.similarity is None else f"{s.similarity:.3f}"
        lines.append(f"| `{s.scenario_id}` | {st} | {s.score} | {sim} |")
    lines.append("")
    lines.append("</details>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _score_release(contract_pass_rate: float, similarity: float | None) -> int:
    similarity_component = 1.0 if similarity is None else similarity
    raw_score = (contract_pass_rate * 70.0) + (similarity_component * 30.0)
    return int(round(raw_score))
