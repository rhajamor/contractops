from contractops.models import (
    CheckResult,
    ContractEvaluation,
    RunResult,
    Scenario,
    ScenarioReport,
    SuiteResult,
)


class TestScenario:
    def test_matches_tags_with_overlap(self):
        s = Scenario(id="x", description="d", input="i", expected={}, tags=["a", "b"])
        assert s.matches_tags(["b", "c"]) is True

    def test_matches_tags_no_overlap(self):
        s = Scenario(id="x", description="d", input="i", expected={}, tags=["a"])
        assert s.matches_tags(["b"]) is False

    def test_matches_tags_empty_required(self):
        s = Scenario(id="x", description="d", input="i", expected={}, tags=["a"])
        assert s.matches_tags([]) is True

    def test_to_dict(self):
        s = Scenario(id="x", description="d", input="i", expected={"a": 1}, tags=["t"])
        d = s.to_dict()
        assert d["id"] == "x"
        assert d["tags"] == ["t"]


class TestRunResult:
    def test_to_dict(self):
        r = RunResult(
            scenario_id="s1", executor="mock-v1", output="out", latency_ms=10,
            tool_calls=["t1"],
        )
        d = r.to_dict()
        assert d["scenario_id"] == "s1"
        assert d["tool_calls"] == ["t1"]


class TestContractEvaluation:
    def test_pass_rate_all_pass(self):
        checks = [CheckResult("a", True, ""), CheckResult("b", True, "")]
        ev = ContractEvaluation(passed=True, checks=checks)
        assert ev.pass_rate == 1.0

    def test_pass_rate_half_fail(self):
        checks = [CheckResult("a", True, ""), CheckResult("b", False, "")]
        ev = ContractEvaluation(passed=False, checks=checks)
        assert ev.pass_rate == 0.5

    def test_pass_rate_empty(self):
        ev = ContractEvaluation(passed=True, checks=[])
        assert ev.pass_rate == 1.0


class TestSuiteResult:
    def test_pass_rate(self):
        sr = SuiteResult(passed=False, total=4, passed_count=3, failed_count=1, score=80)
        assert sr.pass_rate == 0.75

    def test_failed_scenarios(self):
        s1 = ScenarioReport(
            scenario_id="a", passed=True, score=90, contract_pass_rate=1.0,
            similarity=None, latency_ms=10, executor="mock-v1", reasons=[],
            checks=[], candidate_output="", diff_preview=[], diff_truncated=False,
            tool_calls=[],
        )
        s2 = ScenarioReport(
            scenario_id="b", passed=False, score=50, contract_pass_rate=0.5,
            similarity=None, latency_ms=20, executor="mock-v1", reasons=["fail"],
            checks=[], candidate_output="", diff_preview=[], diff_truncated=False,
            tool_calls=[],
        )
        sr = SuiteResult(
            passed=False, total=2, passed_count=1, failed_count=1,
            score=70, scenarios=[s1, s2],
        )
        failed = sr.failed_scenarios()
        assert len(failed) == 1
        assert failed[0].scenario_id == "b"
