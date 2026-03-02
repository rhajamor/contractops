"""Contract assertion engine.

Evaluates scenario expectations against run results. Supports:
- must_include / must_not_include: phrase presence checks
- regex: pattern matching
- max_chars / min_chars: output length bounds
- max_latency_ms: performance threshold
- required_tools: tool call verification
- json_schema: structural validation of output
- sentiment_positive: basic positive-tone check
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from contractops.models import CheckResult, ContractEvaluation, RunResult, Scenario


def evaluate_contracts(scenario: Scenario, result: RunResult) -> ContractEvaluation:
    expected = scenario.expected
    output = result.output
    output_lower = output.lower()
    checks: list[CheckResult] = []

    for phrase in _as_list(expected.get("must_include")):
        target = str(phrase)
        passed = target.lower() in output_lower
        checks.append(
            CheckResult(
                name=f"must_include:{target}",
                passed=passed,
                detail="Found required phrase." if passed else "Missing required phrase.",
            )
        )

    for phrase in _as_list(expected.get("must_not_include")):
        target = str(phrase)
        passed = target.lower() not in output_lower
        checks.append(
            CheckResult(
                name=f"must_not_include:{target}",
                passed=passed,
                detail="Forbidden phrase not present." if passed else "Forbidden phrase detected.",
            )
        )

    for pattern in _as_list(expected.get("regex")):
        regex = str(pattern)
        matched = re.search(regex, output, flags=re.IGNORECASE) is not None
        checks.append(
            CheckResult(
                name=f"regex:{regex}",
                passed=matched,
                detail="Pattern matched output." if matched else "Pattern did not match output.",
            )
        )

    if "max_chars" in expected:
        max_chars = int(expected["max_chars"])
        passed = len(output) <= max_chars
        checks.append(
            CheckResult(
                name=f"max_chars:{max_chars}",
                passed=passed,
                detail=f"Output length is {len(output)} chars (limit {max_chars}).",
            )
        )

    if "min_chars" in expected:
        min_chars = int(expected["min_chars"])
        passed = len(output) >= min_chars
        checks.append(
            CheckResult(
                name=f"min_chars:{min_chars}",
                passed=passed,
                detail=f"Output length is {len(output)} chars (minimum {min_chars}).",
            )
        )

    if "max_latency_ms" in expected:
        max_latency = int(expected["max_latency_ms"])
        passed = result.latency_ms <= max_latency
        checks.append(
            CheckResult(
                name=f"max_latency_ms:{max_latency}",
                passed=passed,
                detail=f"Latency was {result.latency_ms}ms (limit {max_latency}ms).",
            )
        )

    required_tools = [str(t) for t in _as_list(expected.get("required_tools"))]
    if required_tools:
        used_tools = set(result.tool_calls)
        for tool in required_tools:
            passed = tool in used_tools
            checks.append(
                CheckResult(
                    name=f"required_tool:{tool}",
                    passed=passed,
                    detail=(
                        "Required tool was called."
                        if passed
                        else "Required tool was not called."
                    ),
                )
            )

    if "json_schema" in expected:
        checks.append(_check_json_schema(output, expected["json_schema"]))

    if expected.get("sentiment_positive"):
        checks.append(_check_sentiment_positive(output))

    passed = all(c.passed for c in checks)
    return ContractEvaluation(passed=passed, checks=checks)


def _check_json_schema(output: str, schema: dict[str, Any]) -> CheckResult:
    import json

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as exc:
        return CheckResult(
            name="json_schema",
            passed=False,
            detail=f"Output is not valid JSON: {exc}",
        )

    try:
        import jsonschema

        jsonschema.validate(parsed, schema)
        return CheckResult(name="json_schema", passed=True, detail="Output matches JSON schema.")
    except jsonschema.ValidationError as exc:
        return CheckResult(
            name="json_schema",
            passed=False,
            detail=f"JSON schema validation failed: {exc.message}",
        )


_NEGATIVE_MARKERS = [
    "i cannot", "i can't", "unfortunately", "i'm sorry",
    "not possible", "unable to", "we cannot", "we can't",
    "i refuse", "not allowed", "denied", "error occurred",
]

_POSITIVE_MARKERS = [
    "i can help", "happy to", "glad to", "here are",
    "certainly", "of course", "absolutely", "sure",
    "next steps", "let me", "i'll", "we'll",
]


def _check_sentiment_positive(output: str) -> CheckResult:
    lower = output.lower()
    neg_count = sum(1 for m in _NEGATIVE_MARKERS if m in lower)
    pos_count = sum(1 for m in _POSITIVE_MARKERS if m in lower)
    passed = pos_count >= neg_count and neg_count <= 1
    detail = f"Positive signals: {pos_count}, negative signals: {neg_count}."
    return CheckResult(name="sentiment_positive", passed=passed, detail=detail)


def _as_list(value: object) -> Iterable[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
