from contractops.models import (
    CheckResult,
    ContractEvaluation,
    RunResult,
    Scenario,
    ScenarioReport,
    SuiteResult,
)
from contractops.report import (
    build_release_report,
    render_github_comment,
    render_junit_xml,
    render_markdown,
    render_single_junit_xml,
    render_suite_markdown,
)


def _make_scenario() -> Scenario:
    return Scenario(
        id="test-scenario", description="d", input="i",
        expected={"must_include": ["hello"]},
    )


def _make_run_result() -> RunResult:
    return RunResult(
        scenario_id="test-scenario", executor="mock-v1",
        output="hello world", latency_ms=25,
        tool_calls=["tool.a"],
    )


def _make_eval(passed: bool) -> ContractEvaluation:
    return ContractEvaluation(
        passed=passed,
        checks=[CheckResult("must_include:hello", passed, "detail")],
    )


class TestBuildReleaseReport:
    def test_passing_without_baseline(self):
        report = build_release_report(
            _make_scenario(), _make_run_result(), _make_eval(True),
            baseline_comparison=None, min_similarity=0.85, min_score=80,
        )
        assert report["passed"] is True
        assert report["score"] == 100
        assert report["similarity"] is None

    def test_score_without_baseline_reflects_contracts_only(self):
        half_pass = ContractEvaluation(
            passed=False,
            checks=[
                CheckResult("a", True, "ok"),
                CheckResult("b", False, "fail"),
            ],
        )
        report = build_release_report(
            _make_scenario(), _make_run_result(), half_pass,
            baseline_comparison=None, min_similarity=0.85, min_score=80,
        )
        assert report["score"] == 50

    def test_passing_with_baseline(self):
        report = build_release_report(
            _make_scenario(), _make_run_result(), _make_eval(True),
            baseline_comparison={"similarity": 0.95, "diff_preview": [], "diff_truncated": False},
            min_similarity=0.85, min_score=80,
        )
        assert report["passed"] is True
        assert report["similarity"] == 0.95

    def test_fails_on_contract(self):
        report = build_release_report(
            _make_scenario(), _make_run_result(), _make_eval(False),
            baseline_comparison=None, min_similarity=0.85, min_score=80,
        )
        assert report["passed"] is False
        assert "contract checks failed" in report["reasons"][0]

    def test_fails_on_drift(self):
        report = build_release_report(
            _make_scenario(), _make_run_result(), _make_eval(True),
            baseline_comparison={
                "similarity": 0.50,
                "diff_preview": ["- a", "+ b"],
                "diff_truncated": False,
            },
            min_similarity=0.85, min_score=80,
        )
        assert report["passed"] is False
        assert any("drift" in r.lower() for r in report["reasons"])

    def test_fails_on_score(self):
        report = build_release_report(
            _make_scenario(), _make_run_result(), _make_eval(True),
            baseline_comparison={"similarity": 0.5, "diff_preview": [], "diff_truncated": False},
            min_similarity=0.1, min_score=99,
        )
        assert report["passed"] is False
        assert any("score" in r.lower() for r in report["reasons"])


class TestRenderMarkdown:
    def test_contains_key_elements(self):
        report = build_release_report(
            _make_scenario(), _make_run_result(), _make_eval(True),
            baseline_comparison=None, min_similarity=0.85, min_score=80,
        )
        md = render_markdown(report, 0.85, 80)
        assert "ContractOps Result: PASS" in md
        assert "test-scenario" in md
        assert "mock-v1" in md

    def test_contains_diff_section(self):
        report = build_release_report(
            _make_scenario(), _make_run_result(), _make_eval(True),
            baseline_comparison={
                "similarity": 0.9,
                "diff_preview": ["- old", "+ new"],
                "diff_truncated": False,
            },
            min_similarity=0.85, min_score=80,
        )
        md = render_markdown(report, 0.85, 80)
        assert "Diff Preview" in md


class TestRenderSuiteMarkdown:
    def test_suite_pass(self):
        suite = SuiteResult(
            passed=True, total=2, passed_count=2, failed_count=0, score=95,
            scenarios=[
                ScenarioReport(
                    scenario_id="s1", passed=True, score=95,
                    contract_pass_rate=1.0, similarity=0.9, latency_ms=20,
                    executor="mock-v1", reasons=[], checks=[], candidate_output="ok",
                    diff_preview=[], diff_truncated=False, tool_calls=[],
                ),
                ScenarioReport(
                    scenario_id="s2", passed=True, score=95,
                    contract_pass_rate=1.0, similarity=0.9, latency_ms=20,
                    executor="mock-v1", reasons=[], checks=[], candidate_output="ok",
                    diff_preview=[], diff_truncated=False, tool_calls=[],
                ),
            ],
        )
        md = render_suite_markdown(suite, 0.85, 80)
        assert "PASS" in md
        assert "2" in md


class TestRenderJunitXml:
    def test_basic_xml(self):
        suite = SuiteResult(
            passed=False, total=2, passed_count=1, failed_count=1, score=70,
            scenarios=[
                ScenarioReport(
                    scenario_id="s1", passed=True, score=90,
                    contract_pass_rate=1.0, similarity=None, latency_ms=20,
                    executor="mock-v1", reasons=[], checks=[], candidate_output="ok",
                    diff_preview=[], diff_truncated=False, tool_calls=[],
                ),
                ScenarioReport(
                    scenario_id="s2", passed=False, score=50,
                    contract_pass_rate=0.5, similarity=None, latency_ms=30,
                    executor="mock-v2", reasons=["contract failed"],
                    checks=[{"name": "must_include:x", "passed": False, "detail": "missing"}],
                    candidate_output="bad", diff_preview=[], diff_truncated=False, tool_calls=[],
                ),
            ],
        )
        xml = render_junit_xml(suite)
        assert "<?xml" in xml
        assert "testsuites" in xml
        assert "testcase" in xml
        assert 'name="s2"' in xml
        assert "failure" in xml


class TestRenderSingleJunitXml:
    def test_passing_report(self):
        report = build_release_report(
            _make_scenario(), _make_run_result(), _make_eval(True),
            baseline_comparison=None, min_similarity=0.85, min_score=80,
        )
        xml = render_single_junit_xml(report)
        assert "<?xml" in xml
        assert "testsuites" in xml
        assert "testcase" in xml
        assert 'name="test-scenario"' in xml
        assert 'failures="0"' in xml
        assert "<failure" not in xml

    def test_failing_report(self):
        report = build_release_report(
            _make_scenario(), _make_run_result(), _make_eval(False),
            baseline_comparison=None, min_similarity=0.85, min_score=80,
        )
        xml = render_single_junit_xml(report)
        assert "<?xml" in xml
        assert "failure" in xml


class TestRenderGithubComment:
    def test_pass(self):
        suite = SuiteResult(passed=True, total=1, passed_count=1, failed_count=0, score=90)
        comment = render_github_comment(suite, 0.85, 80)
        assert "PASS" in comment
        assert "1/1" in comment

    def test_fail_shows_details(self):
        suite = SuiteResult(
            passed=False, total=1, passed_count=0, failed_count=1, score=50,
            scenarios=[
                ScenarioReport(
                    scenario_id="bad", passed=False, score=50,
                    contract_pass_rate=0.5, similarity=None, latency_ms=10,
                    executor="mock-v2", reasons=["failed"], checks=[],
                    candidate_output="", diff_preview=[], diff_truncated=False, tool_calls=[],
                ),
            ],
        )
        comment = render_github_comment(suite, 0.85, 80)
        assert "FAIL" in comment
        assert "bad" in comment
