"""Tests for orchestration adapters (LangGraph, CrewAI, Trace)."""

from __future__ import annotations

from typing import Any

from contractops.adapters import (
    CrewAIExecutor,
    LangGraphExecutor,
    TraceCapture,
    TraceExecutor,
)
from contractops.models import Scenario


def _make_scenario() -> Scenario:
    return Scenario(
        id="adapter-test",
        description="Adapter test scenario",
        input="Help me with my account.",
        expected={"must_include": ["help"]},
    )


class TestTraceCapture:
    def test_record_tool(self) -> None:
        trace = TraceCapture()
        trace.record_tool("tool.lookup", {"key": "value"})
        assert "tool.lookup" in trace.tool_calls
        assert len(trace.steps) == 1
        assert trace.steps[0]["type"] == "tool_call"

    def test_record_step(self) -> None:
        trace = TraceCapture()
        trace.record_step("reasoning", "thinking about the problem")
        assert len(trace.steps) == 1
        assert trace.steps[0]["type"] == "reasoning"

    def test_multiple_records(self) -> None:
        trace = TraceCapture()
        trace.record_tool("tool.a")
        trace.record_tool("tool.b")
        trace.record_step("output", "done")
        assert len(trace.tool_calls) == 2
        assert len(trace.steps) == 3


class TestTraceExecutor:
    def test_string_return(self) -> None:
        def run_fn(input_text: str) -> str:
            return f"Response to: {input_text}"

        executor = TraceExecutor(run_fn, name="test-trace")
        result = executor.run(_make_scenario())
        assert result.executor == "test-trace"
        assert "Response to:" in result.output
        assert result.latency_ms >= 0

    def test_dict_return(self) -> None:
        def run_fn(input_text: str) -> dict[str, Any]:
            return {
                "output": "I can help with that.",
                "tool_calls": ["tool.account_lookup"],
            }

        executor = TraceExecutor(run_fn, name="dict-trace")
        result = executor.run(_make_scenario())
        assert "help" in result.output.lower()
        assert "tool.account_lookup" in result.tool_calls

    def test_error_handling(self) -> None:
        def run_fn(input_text: str) -> str:
            raise RuntimeError("Test error")

        executor = TraceExecutor(run_fn, name="error-trace")
        result = executor.run(_make_scenario())
        assert "error" in result.output.lower()
        assert result.latency_ms >= 0

    def test_extra_metadata(self) -> None:
        def run_fn(input_text: str) -> dict[str, Any]:
            return {
                "output": "done",
                "tool_calls": [],
                "extra": {"tokens": 42},
            }

        executor = TraceExecutor(run_fn, name="meta-trace")
        result = executor.run(_make_scenario())
        assert result.extra.get("tokens") == 42


class TestLangGraphExecutor:
    def test_with_mock_graph(self) -> None:
        class MockGraph:
            def invoke(self, input_data: dict) -> dict:
                return {
                    "messages": [
                        {"role": "assistant", "content": "I can help you with your account."}
                    ]
                }

        executor = LangGraphExecutor(MockGraph(), name="mock-langgraph")
        result = executor.run(_make_scenario())
        assert "help" in result.output.lower()
        assert result.executor == "mock-langgraph"

    def test_with_error_graph(self) -> None:
        class ErrorGraph:
            def invoke(self, input_data: dict) -> dict:
                raise RuntimeError("Graph execution failed")

        executor = LangGraphExecutor(ErrorGraph(), name="error-graph")
        result = executor.run(_make_scenario())
        assert "error" in result.output.lower()

    def test_extracts_tool_calls(self) -> None:
        class ToolGraph:
            def invoke(self, input_data: dict) -> dict:
                return {
                    "messages": [
                        {"type": "tool", "name": "search_db", "content": "results"},
                        {"role": "assistant", "content": "Found your account."},
                    ]
                }

        executor = LangGraphExecutor(ToolGraph())
        result = executor.run(_make_scenario())
        assert "search_db" in result.tool_calls


class TestCrewAIExecutor:
    def test_with_mock_crew(self) -> None:
        class MockResult:
            raw = "The crew has completed the task and can help you."

        class MockCrew:
            def kickoff(self, inputs: dict) -> MockResult:
                return MockResult()

        executor = CrewAIExecutor(MockCrew(), name="mock-crew")
        result = executor.run(_make_scenario())
        assert "help" in result.output.lower()
        assert result.executor == "mock-crew"

    def test_string_result(self) -> None:
        class MockCrew:
            def kickoff(self, inputs: dict) -> str:
                return "Direct string response with help."

        executor = CrewAIExecutor(MockCrew(), name="string-crew")
        result = executor.run(_make_scenario())
        assert "help" in result.output.lower()

    def test_error_handling(self) -> None:
        class ErrorCrew:
            def kickoff(self, inputs: dict) -> str:
                raise RuntimeError("Crew execution failed")

        executor = CrewAIExecutor(ErrorCrew(), name="error-crew")
        result = executor.run(_make_scenario())
        assert "error" in result.output.lower()
