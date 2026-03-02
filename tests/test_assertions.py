import json

from contractops.assertions import evaluate_contracts
from contractops.models import RunResult, Scenario


def _make_scenario(expected: dict) -> Scenario:
    return Scenario(id="t", description="d", input="i", expected=expected)


def _make_result(
    output: str,
    tool_calls: list[str] | None = None,
    latency_ms: int = 20,
) -> RunResult:
    return RunResult(
        scenario_id="t", executor="test", output=output,
        latency_ms=latency_ms, tool_calls=tool_calls or [],
    )


class TestMustInclude:
    def test_passes_when_present(self):
        s = _make_scenario({"must_include": ["hello"]})
        r = _make_result("Hello world!")
        ev = evaluate_contracts(s, r)
        assert ev.passed

    def test_fails_when_missing(self):
        s = _make_scenario({"must_include": ["goodbye"]})
        r = _make_result("Hello world!")
        ev = evaluate_contracts(s, r)
        assert not ev.passed

    def test_case_insensitive(self):
        s = _make_scenario({"must_include": ["HELLO"]})
        r = _make_result("hello there")
        assert evaluate_contracts(s, r).passed

    def test_multiple_phrases(self):
        s = _make_scenario({"must_include": ["a", "b", "c"]})
        r = _make_result("a b c d")
        assert evaluate_contracts(s, r).passed
        r2 = _make_result("a b d")
        assert not evaluate_contracts(s, r2).passed


class TestMustNotInclude:
    def test_passes_when_absent(self):
        s = _make_scenario({"must_not_include": ["error"]})
        r = _make_result("All good.")
        assert evaluate_contracts(s, r).passed

    def test_fails_when_present(self):
        s = _make_scenario({"must_not_include": ["error"]})
        r = _make_result("An error occurred.")
        assert not evaluate_contracts(s, r).passed


class TestRegex:
    def test_matches(self):
        s = _make_scenario({"regex": [r"\d+ business days"]})
        r = _make_result("Expect 5 business days.")
        assert evaluate_contracts(s, r).passed

    def test_no_match(self):
        s = _make_scenario({"regex": [r"\d+ business days"]})
        r = _make_result("Expect some business days.")
        assert not evaluate_contracts(s, r).passed


class TestMaxChars:
    def test_within_limit(self):
        s = _make_scenario({"max_chars": 100})
        r = _make_result("short")
        assert evaluate_contracts(s, r).passed

    def test_exceeds_limit(self):
        s = _make_scenario({"max_chars": 5})
        r = _make_result("too long output")
        assert not evaluate_contracts(s, r).passed


class TestMinChars:
    def test_meets_minimum(self):
        s = _make_scenario({"min_chars": 3})
        r = _make_result("hello")
        assert evaluate_contracts(s, r).passed

    def test_below_minimum(self):
        s = _make_scenario({"min_chars": 100})
        r = _make_result("short")
        assert not evaluate_contracts(s, r).passed


class TestMaxLatencyMs:
    def test_within_limit(self):
        s = _make_scenario({"max_latency_ms": 100})
        r = _make_result("ok", latency_ms=50)
        assert evaluate_contracts(s, r).passed

    def test_exceeds_limit(self):
        s = _make_scenario({"max_latency_ms": 10})
        r = _make_result("ok", latency_ms=50)
        assert not evaluate_contracts(s, r).passed


class TestRequiredTools:
    def test_all_called(self):
        s = _make_scenario({"required_tools": ["tool.a", "tool.b"]})
        r = _make_result("ok", tool_calls=["tool.a", "tool.b", "tool.c"])
        assert evaluate_contracts(s, r).passed

    def test_missing_tool(self):
        s = _make_scenario({"required_tools": ["tool.a", "tool.b"]})
        r = _make_result("ok", tool_calls=["tool.a"])
        assert not evaluate_contracts(s, r).passed


class TestJsonSchema:
    def test_valid_json(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        s = _make_scenario({"json_schema": schema})
        r = _make_result(json.dumps({"name": "Alice"}))
        assert evaluate_contracts(s, r).passed

    def test_invalid_json(self):
        schema = {"type": "object", "required": ["name"]}
        s = _make_scenario({"json_schema": schema})
        r = _make_result("not json at all")
        ev = evaluate_contracts(s, r)
        assert not ev.passed
        assert any("not valid JSON" in c.detail for c in ev.checks)

    def test_schema_mismatch(self):
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer"}},
            "required": ["age"],
        }
        s = _make_scenario({"json_schema": schema})
        r = _make_result(json.dumps({"name": "Bob"}))
        ev = evaluate_contracts(s, r)
        assert not ev.passed


class TestSentimentPositive:
    def test_positive_output(self):
        s = _make_scenario({"sentiment_positive": True})
        r = _make_result("I can help you with that. Here are the next steps.")
        assert evaluate_contracts(s, r).passed

    def test_negative_output(self):
        s = _make_scenario({"sentiment_positive": True})
        r = _make_result("I cannot help. Unfortunately this is not possible. I'm sorry.")
        assert not evaluate_contracts(s, r).passed


class TestCombined:
    def test_full_contract_pass(self, customer_scenario, passing_run_result):
        ev = evaluate_contracts(customer_scenario, passing_run_result)
        assert ev.passed
        assert ev.pass_rate == 1.0

    def test_full_contract_fail(self, customer_scenario, failing_run_result):
        ev = evaluate_contracts(customer_scenario, failing_run_result)
        assert not ev.passed
        assert ev.pass_rate < 1.0

    def test_empty_expected(self):
        s = _make_scenario({})
        r = _make_result("anything")
        ev = evaluate_contracts(s, r)
        assert ev.passed
        assert ev.checks == []
