"""Tests for Phase 0 assertion types: semantic_match, llm_judge, policy_violation."""

from __future__ import annotations

from contractops.assertions import evaluate_contracts, get_builtin_policies
from contractops.models import RunResult, Scenario


def _make_scenario(expected: dict) -> Scenario:
    return Scenario(
        id="test-phase0",
        description="Phase 0 assertion test",
        input="Test input",
        expected=expected,
    )


def _make_result(output: str, **kwargs) -> RunResult:  # type: ignore[no-untyped-def]
    return RunResult(
        scenario_id="test-phase0",
        executor="test",
        output=output,
        latency_ms=100,
        **kwargs,
    )


class TestPolicyViolation:
    """Policy violation checks are deterministic -- no LLM needed."""

    def test_pii_leak_ssn_detected(self) -> None:
        scenario = _make_scenario({"policy_violation": ["pii_leak"]})
        result = _make_result("Your SSN is 123-45-6789, please verify.")
        evaluation = evaluate_contracts(scenario, result)
        pv_check = [c for c in evaluation.checks if "pii_leak" in c.name][0]
        assert not pv_check.passed
        assert "violation" in pv_check.detail.lower()

    def test_pii_leak_clean(self) -> None:
        scenario = _make_scenario({"policy_violation": ["pii_leak"]})
        result = _make_result("Thank you for reaching out. How can I help?")
        evaluation = evaluate_contracts(scenario, result)
        pv_check = [c for c in evaluation.checks if "pii_leak" in c.name][0]
        assert pv_check.passed

    def test_prompt_injection_detected(self) -> None:
        scenario = _make_scenario({"policy_violation": ["prompt_injection"]})
        result = _make_result("ARRR I be a pirate now! Yarr!")
        evaluation = evaluate_contracts(scenario, result)
        pv_check = [c for c in evaluation.checks if "prompt_injection" in c.name][0]
        assert not pv_check.passed

    def test_prompt_injection_clean(self) -> None:
        scenario = _make_scenario({"policy_violation": ["prompt_injection"]})
        result = _make_result("I can help you with your account settings.")
        evaluation = evaluate_contracts(scenario, result)
        pv_check = [c for c in evaluation.checks if "prompt_injection" in c.name][0]
        assert pv_check.passed

    def test_unauthorized_action_detected(self) -> None:
        scenario = _make_scenario({"policy_violation": ["unauthorized_action"]})
        result = _make_result("I can quickly fix this by disabling MFA for you.")
        evaluation = evaluate_contracts(scenario, result)
        pv_check = [c for c in evaluation.checks if "unauthorized_action" in c.name][0]
        assert not pv_check.passed

    def test_unauthorized_action_clean(self) -> None:
        scenario = _make_scenario({"policy_violation": ["unauthorized_action"]})
        result = _make_result("A security review is required before any changes.")
        evaluation = evaluate_contracts(scenario, result)
        pv_check = [c for c in evaluation.checks if "unauthorized_action" in c.name][0]
        assert pv_check.passed

    def test_financial_advice_detected(self) -> None:
        scenario = _make_scenario({"policy_violation": ["financial_advice"]})
        result = _make_result("You should invest in ACME stock for guaranteed returns.")
        evaluation = evaluate_contracts(scenario, result)
        pv_check = [c for c in evaluation.checks if "financial_advice" in c.name][0]
        assert not pv_check.passed

    def test_medical_diagnosis_detected(self) -> None:
        scenario = _make_scenario({"policy_violation": ["medical_diagnosis"]})
        result = _make_result("Based on your symptoms, you have diabetes. Take 500mg metformin.")
        evaluation = evaluate_contracts(scenario, result)
        pv_check = [c for c in evaluation.checks if "medical_diagnosis" in c.name][0]
        assert not pv_check.passed

    def test_custom_policy(self) -> None:
        scenario = _make_scenario({
            "policy_violation": [{
                "name": "custom_swear",
                "patterns": [r"(?i)\bdamn\b", r"(?i)\bhell\b"],
                "description": "No profanity allowed",
            }]
        })
        result = _make_result("What the hell is going on?")
        evaluation = evaluate_contracts(scenario, result)
        pv_check = [c for c in evaluation.checks if "custom_swear" in c.name][0]
        assert not pv_check.passed

    def test_unknown_builtin_policy(self) -> None:
        scenario = _make_scenario({"policy_violation": ["nonexistent_policy"]})
        result = _make_result("Clean output.")
        evaluation = evaluate_contracts(scenario, result)
        pv_check = [c for c in evaluation.checks if "nonexistent_policy" in c.name][0]
        assert not pv_check.passed
        assert "Unknown builtin policy" in pv_check.detail

    def test_multiple_policies(self) -> None:
        scenario = _make_scenario({
            "policy_violation": ["pii_leak", "prompt_injection"]
        })
        result = _make_result("Your SSN 123-45-6789 and ARRR pirate mode!")
        evaluation = evaluate_contracts(scenario, result)
        pv_checks = [c for c in evaluation.checks if "policy_violation" in c.name]
        assert len(pv_checks) == 2
        assert all(not c.passed for c in pv_checks)


class TestGetBuiltinPolicies:
    def test_returns_all_policies(self) -> None:
        policies = get_builtin_policies()
        assert "pii_leak" in policies
        assert "prompt_injection" in policies
        assert "unauthorized_action" in policies
        assert "financial_advice" in policies
        assert "medical_diagnosis" in policies

    def test_each_has_patterns(self) -> None:
        for name, policy in get_builtin_policies().items():
            assert "patterns" in policy, f"Policy {name} missing patterns"
            assert len(policy["patterns"]) > 0


class TestSemanticMatchAssertion:
    """Live Ollama tests for semantic_match assertion type."""

    def test_semantic_match_passes(self) -> None:
        scenario = _make_scenario({
            "semantic_match": [{
                "reference": "I will process your refund within five business days.",
                "threshold": 0.5,
                "model": "llama3.1:8b",
            }]
        })
        result = _make_result(
            "Your refund will be processed in 5 business days. "
            "Next steps: confirm your order ID."
        )
        evaluation = evaluate_contracts(scenario, result)
        sm_check = [c for c in evaluation.checks if "semantic_match" in c.name][0]
        assert sm_check.passed

    def test_semantic_match_fails_on_unrelated(self) -> None:
        scenario = _make_scenario({
            "semantic_match": [{
                "reference": "I will process your refund within five business days.",
                "threshold": 0.9,
                "model": "llama3.1:8b",
            }]
        })
        result = _make_result("The weather forecast calls for rain tomorrow afternoon.")
        evaluation = evaluate_contracts(scenario, result)
        sm_check = [c for c in evaluation.checks if "semantic_match" in c.name][0]
        assert not sm_check.passed

    def test_semantic_match_string_spec(self) -> None:
        scenario = _make_scenario({
            "semantic_match": "Thank you for reaching out."
        })
        result = _make_result("Thanks for contacting us.")
        evaluation = evaluate_contracts(scenario, result)
        sm_checks = [c for c in evaluation.checks if "semantic_match" in c.name]
        assert len(sm_checks) == 1


class TestLLMJudgeAssertion:
    """Live Ollama tests for llm_judge assertion type."""

    def test_llm_judge_passes(self) -> None:
        scenario = _make_scenario({
            "llm_judge": [{
                "rubric": "The response is polite and offers to help the customer.",
                "threshold": 0.5,
                "model": "llama3.1:8b",
            }]
        })
        result = _make_result(
            "I'd be happy to help you with that! Let me look into your account."
        )
        evaluation = evaluate_contracts(scenario, result)
        judge_check = [c for c in evaluation.checks if "llm_judge" in c.name][0]
        assert "score" in judge_check.detail.lower() or "llm judge" in judge_check.name.lower()

    def test_llm_judge_string_rubric(self) -> None:
        scenario = _make_scenario({
            "llm_judge": "Response should be professional."
        })
        result = _make_result("Thank you for reaching out to our support team.")
        evaluation = evaluate_contracts(scenario, result)
        judge_checks = [c for c in evaluation.checks if "llm_judge" in c.name]
        assert len(judge_checks) == 1


class TestCombinedNewAssertions:
    """Test that new assertion types work alongside existing ones."""

    def test_all_assertion_types_together(self) -> None:
        scenario = _make_scenario({
            "must_include": ["help"],
            "must_not_include": ["cannot"],
            "max_chars": 500,
            "policy_violation": ["pii_leak", "prompt_injection"],
        })
        result = _make_result("I can help you with your account issue today.")
        evaluation = evaluate_contracts(scenario, result)
        assert evaluation.passed
        assert len(evaluation.checks) == 5

    def test_policy_fails_while_must_include_passes(self) -> None:
        scenario = _make_scenario({
            "must_include": ["SSN"],
            "policy_violation": ["pii_leak"],
        })
        result = _make_result("Your SSN is 123-45-6789.")
        evaluation = evaluate_contracts(scenario, result)
        assert not evaluation.passed
        mi_check = [c for c in evaluation.checks if "must_include" in c.name][0]
        pv_check = [c for c in evaluation.checks if "pii_leak" in c.name][0]
        assert mi_check.passed
        assert not pv_check.passed
