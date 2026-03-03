"""Orchestration framework adapters for LangGraph, CrewAI, and generic trace-based agents.

These adapters wrap various agentic frameworks as ContractOps executors, enabling
contract testing across the full spectrum of modern AI orchestration tools.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from contractops.models import RunResult, Scenario

logger = logging.getLogger("contractops.adapters")


class TraceCapture:
    """Captures tool calls and intermediate steps from agent execution traces."""

    def __init__(self) -> None:
        self.tool_calls: list[str] = []
        self.steps: list[dict[str, Any]] = []

    def record_tool(self, name: str, args: dict[str, Any] | None = None) -> None:
        self.tool_calls.append(name)
        self.steps.append({
            "type": "tool_call",
            "name": name,
            "args": args or {},
            "timestamp": time.time(),
        })

    def record_step(self, step_type: str, content: str) -> None:
        self.steps.append({
            "type": step_type,
            "content": content,
            "timestamp": time.time(),
        })


class LangGraphExecutor:
    """Wraps a LangGraph compiled graph as a ContractOps executor.

    Usage:
        from langgraph.graph import StateGraph
        graph = StateGraph(...)  # your compiled graph
        executor = LangGraphExecutor(graph, name="my-agent")
    """

    def __init__(
        self,
        graph: Any,
        name: str = "langgraph",
        input_key: str = "messages",
        output_key: str = "messages",
    ) -> None:
        self.name = name
        self._graph = graph
        self._input_key = input_key
        self._output_key = output_key

    def run(self, scenario: Scenario) -> RunResult:
        trace = TraceCapture()
        start = time.perf_counter()

        try:
            if self._input_key == "messages":
                input_data = {self._input_key: [{"role": "user", "content": scenario.input}]}
            else:
                input_data = {self._input_key: scenario.input}

            result = self._graph.invoke(input_data)
            latency_ms = int((time.perf_counter() - start) * 1000)

            output = self._extract_output(result)
            tool_calls = self._extract_tool_calls(result)

        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.error("LangGraph execution failed: %s", exc)
            output = f"Execution error: {exc}"
            tool_calls = []

        return RunResult(
            scenario_id=scenario.id,
            executor=self.name,
            output=output,
            latency_ms=latency_ms,
            tool_calls=tool_calls + trace.tool_calls,
            extra={"adapter": "langgraph", "steps": len(trace.steps)},
        )

    def _extract_output(self, result: Any) -> str:
        if isinstance(result, dict):
            messages = result.get(self._output_key, [])
            if isinstance(messages, list) and messages:
                last = messages[-1]
                if isinstance(last, dict):
                    return str(last.get("content", str(last)))
                return str(last)
            if "output" in result:
                return str(result["output"])
            return json.dumps(result, default=str)
        return str(result)

    def _extract_tool_calls(self, result: Any) -> list[str]:
        calls: list[str] = []
        if isinstance(result, dict):
            messages = result.get(self._output_key, [])
            if isinstance(messages, list):
                for msg in messages:
                    if isinstance(msg, dict) and msg.get("type") == "tool":
                        calls.append(str(msg.get("name", "unknown_tool")))
        return calls


class CrewAIExecutor:
    """Wraps a CrewAI Crew as a ContractOps executor.

    Usage:
        from crewai import Crew
        crew = Crew(agents=[...], tasks=[...])
        executor = CrewAIExecutor(crew, name="my-crew")
    """

    def __init__(self, crew: Any, name: str = "crewai") -> None:
        self.name = name
        self._crew = crew

    def run(self, scenario: Scenario) -> RunResult:
        start = time.perf_counter()

        try:
            result = self._crew.kickoff(inputs={"input": scenario.input})
            latency_ms = int((time.perf_counter() - start) * 1000)

            if hasattr(result, "raw"):
                output = str(result.raw)
            elif isinstance(result, str):
                output = result
            else:
                output = str(result)

            tool_calls = self._extract_tool_calls(result)

        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.error("CrewAI execution failed: %s", exc)
            output = f"Execution error: {exc}"
            tool_calls = []

        return RunResult(
            scenario_id=scenario.id,
            executor=self.name,
            output=output,
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            extra={"adapter": "crewai"},
        )

    def _extract_tool_calls(self, result: Any) -> list[str]:
        if hasattr(result, "tasks_output"):
            calls: list[str] = []
            for task_output in result.tasks_output:
                if hasattr(task_output, "tools_used"):
                    calls.extend(str(t) for t in task_output.tools_used)
            return calls
        return []


class TraceExecutor:
    """Generic trace-based executor for agent frameworks that produce structured traces.

    Accepts a callable that takes an input string and returns a dict with:
      {"output": "...", "tool_calls": [...], "steps": [...]}
    """

    def __init__(
        self,
        run_fn: Any,
        name: str = "trace",
    ) -> None:
        self.name = name
        self._run_fn = run_fn

    def run(self, scenario: Scenario) -> RunResult:
        start = time.perf_counter()

        try:
            result = self._run_fn(scenario.input)
            latency_ms = int((time.perf_counter() - start) * 1000)

            if isinstance(result, dict):
                output = str(result.get("output", ""))
                tool_calls = list(result.get("tool_calls", []))
                extra = result.get("extra", {})
            elif isinstance(result, str):
                output = result
                tool_calls = []
                extra = {}
            else:
                output = str(result)
                tool_calls = []
                extra = {}

        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            output = f"Execution error: {exc}"
            tool_calls = []
            extra = {"error": str(exc)}

        return RunResult(
            scenario_id=scenario.id,
            executor=self.name,
            output=output,
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            extra={"adapter": "trace", **extra},
        )
