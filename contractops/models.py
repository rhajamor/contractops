from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Scenario:
    id: str
    description: str
    input: str
    expected: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def matches_tags(self, required: list[str]) -> bool:
        if not required:
            return True
        return bool(set(required) & set(self.tags))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunResult:
    scenario_id: str
    executor: str
    output: str
    latency_ms: int
    tool_calls: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ContractEvaluation:
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if not self.checks:
            return 1.0
        passed = sum(1 for c in self.checks if c.passed)
        return passed / len(self.checks)


@dataclass
class TrialResult:
    """Result of a single trial within a multi-trial run."""

    trial_index: int
    passed: bool
    score: int
    contract_pass_rate: float
    similarity: float | None
    latency_ms: int
    output: str


@dataclass
class StabilityMetrics:
    """Statistical metrics across multiple trials of the same scenario."""

    trials_run: int
    trials_passed: int
    pass_rate: float
    mean_score: float
    score_variance: float
    score_stddev: float
    mean_latency_ms: float
    latency_variance: float
    is_flaky: bool
    flaky_reason: str
    trial_results: list[TrialResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScenarioReport:
    """Full result for a single scenario run."""

    scenario_id: str
    passed: bool
    score: int
    contract_pass_rate: float
    similarity: float | None
    latency_ms: int
    executor: str
    reasons: list[str]
    checks: list[dict[str, Any]]
    candidate_output: str
    diff_preview: list[str]
    diff_truncated: bool
    tool_calls: list[str]
    stability: StabilityMetrics | None = None


@dataclass
class SuiteResult:
    """Aggregated result across multiple scenarios."""

    passed: bool
    total: int
    passed_count: int
    failed_count: int
    score: float
    scenarios: list[ScenarioReport] = field(default_factory=list)
    flaky_count: int = 0

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 1.0
        return self.passed_count / self.total

    def failed_scenarios(self) -> list[ScenarioReport]:
        return [s for s in self.scenarios if not s.passed]

    def flaky_scenarios(self) -> list[ScenarioReport]:
        return [
            s for s in self.scenarios
            if s.stability is not None and s.stability.is_flaky
        ]
