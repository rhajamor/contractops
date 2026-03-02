"""Execution backends for running scenarios against AI agents.

Supported:
- mock-v1, mock-v2: deterministic test variants
- openai[:model]: OpenAI-compatible API
- anthropic[:model]: Anthropic Claude API
- ollama[:model]: Local Ollama server (OpenAI-compatible)
- langchain: wraps a LangChain Runnable
- http: generic HTTP/webhook executor
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

from contractops.models import RunResult, Scenario


class Executor(Protocol):
    name: str

    def run(self, scenario: Scenario) -> RunResult: ...


class MockExecutor:
    def __init__(self, variant: str) -> None:
        self.variant = variant
        self.name = f"mock-{variant}"

    def run(self, scenario: Scenario) -> RunResult:
        start = time.perf_counter()
        output, tool_calls = _build_mock_response(self.variant, scenario.input)
        latency_ms = int((time.perf_counter() - start) * 1000) + (
            24 if self.variant == "v1" else 38
        )
        return RunResult(
            scenario_id=scenario.id,
            executor=self.name,
            output=output,
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            extra={"variant": self.variant},
        )


class OpenAICompatibleExecutor:
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        api_key_env: str = "OPENAI_API_KEY",
        system_prompt: str | None = None,
        temperature: float = 0.2,
        timeout: int = 60,
    ) -> None:
        self.name = f"openai:{model}"
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.system_prompt = system_prompt or (
            "You are an enterprise support agent. "
            "Follow policy-safe, concrete, next-step-oriented responses."
        )
        self.temperature = temperature
        self.timeout = timeout

    def run(self, scenario: Scenario) -> RunResult:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing {self.api_key_env}. Set this env var to use the openai executor."
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": scenario.input},
            ],
            "temperature": self.temperature,
        }

        start = time.perf_counter()
        raw = _http_json_request(
            url=f"{self.base_url}/chat/completions",
            body=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=self.timeout,
        )
        output = (
            raw.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        return RunResult(
            scenario_id=scenario.id,
            executor=self.name,
            output=output,
            latency_ms=latency_ms,
            tool_calls=["llm.chat.completions"],
            extra={"model": self.model},
        )


class AnthropicExecutor:
    """Calls the Anthropic Messages API directly via HTTP."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key_env: str = "ANTHROPIC_API_KEY",
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: int = 60,
    ) -> None:
        self.name = f"anthropic:{model}"
        self.model = model
        self.api_key_env = api_key_env
        self.system_prompt = system_prompt or (
            "You are an enterprise support agent. "
            "Follow policy-safe, concrete, next-step-oriented responses."
        )
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    def run(self, scenario: Scenario) -> RunResult:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing {self.api_key_env}. Set this env var to use the anthropic executor."
            )

        payload = {
            "model": self.model,
            "system": self.system_prompt,
            "messages": [{"role": "user", "content": scenario.input}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        start = time.perf_counter()
        raw = _http_json_request(
            url="https://api.anthropic.com/v1/messages",
            body=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=self.timeout,
        )
        blocks = raw.get("content", [])
        output = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        latency_ms = int((time.perf_counter() - start) * 1000)
        return RunResult(
            scenario_id=scenario.id,
            executor=self.name,
            output=output,
            latency_ms=latency_ms,
            tool_calls=["llm.anthropic.messages"],
            extra={"model": self.model},
        )


class OllamaExecutor:
    """Calls a locally-running Ollama server via its OpenAI-compatible API."""

    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        timeout: int = 120,
        num_ctx: int = 4096,
    ) -> None:
        self.name = f"ollama:{model}"
        self.model = model
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.system_prompt = system_prompt or (
            "You are an enterprise support agent. "
            "Follow policy-safe, concrete, next-step-oriented responses."
        )
        self.temperature = temperature
        self.timeout = timeout
        self.num_ctx = num_ctx

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def run(self, scenario: Scenario) -> RunResult:
        if not self.is_available():
            raise RuntimeError(
                f"Ollama server not reachable at {self.base_url}. "
                "Start it with: ollama serve"
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": scenario.input},
            ],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
            },
        }

        start = time.perf_counter()
        raw = _http_json_request(
            url=f"{self.base_url}/api/chat",
            body=payload,
            timeout=self.timeout,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        output = raw.get("message", {}).get("content", "").strip()

        extra: dict[str, Any] = {"model": self.model}
        if "eval_count" in raw:
            extra["tokens_generated"] = raw["eval_count"]
        if "eval_duration" in raw:
            extra["tokens_per_second"] = round(
                raw["eval_count"] / (raw["eval_duration"] / 1e9), 2
            )
        if "prompt_eval_count" in raw:
            extra["prompt_tokens"] = raw["prompt_eval_count"]

        return RunResult(
            scenario_id=scenario.id,
            executor=self.name,
            output=output,
            latency_ms=latency_ms,
            tool_calls=["llm.ollama.chat"],
            extra=extra,
        )


class LangChainExecutor:
    """Wraps a LangChain Runnable (chain, agent, etc.) as a ContractOps executor."""

    def __init__(self, runnable: Any, name: str = "langchain") -> None:
        self.name = name
        self._runnable = runnable

    def run(self, scenario: Scenario) -> RunResult:
        start = time.perf_counter()
        response = self._runnable.invoke({"input": scenario.input})
        latency_ms = int((time.perf_counter() - start) * 1000)

        if isinstance(response, str):
            output = response
            tool_calls: list[str] = []
        elif isinstance(response, dict):
            output = str(response.get("output", response.get("text", str(response))))
            tool_calls = list(response.get("tool_calls", []))
        else:
            output = str(response)
            tool_calls = []

        return RunResult(
            scenario_id=scenario.id,
            executor=self.name,
            output=output,
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            extra={"type": "langchain"},
        )


class HttpExecutor:
    """Generic HTTP executor for any webhook/API endpoint.

    Expects the endpoint to accept JSON with {"input": "..."} and return
    JSON with {"output": "...", "tool_calls": [...]}.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        method: str = "POST",
        timeout: int = 30,
        name: str = "http",
    ) -> None:
        self.name = name
        self.url = url
        self.headers = headers or {}
        self.method = method
        self.timeout = timeout

    def run(self, scenario: Scenario) -> RunResult:
        payload = {
            "input": scenario.input,
            "scenario_id": scenario.id,
            "metadata": scenario.metadata,
        }
        start = time.perf_counter()
        raw = _http_json_request(
            url=self.url,
            body=payload,
            headers=self.headers,
            timeout=self.timeout,
            method=self.method,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        return RunResult(
            scenario_id=scenario.id,
            executor=self.name,
            output=str(raw.get("output", "")),
            latency_ms=latency_ms,
            tool_calls=list(raw.get("tool_calls", [])),
            extra=raw.get("extra", {}),
        )


def build_executor(name: str, **kwargs: Any) -> Executor:
    """Factory for building executors from a name string."""
    normalized = name.strip().lower()

    if normalized == "mock-v1":
        return MockExecutor("v1")
    if normalized == "mock-v2":
        return MockExecutor("v2")
    if normalized.startswith("openai"):
        _, _, model = normalized.partition(":")
        return OpenAICompatibleExecutor(model=model or "gpt-4o-mini", **kwargs)
    if normalized.startswith("anthropic"):
        _, _, model = normalized.partition(":")
        return AnthropicExecutor(model=model or "claude-sonnet-4-20250514", **kwargs)
    if normalized.startswith("ollama"):
        _, _, model = normalized.partition(":")
        return OllamaExecutor(model=model or "llama3.2", **kwargs)
    if normalized.startswith("http"):
        url = kwargs.get("url")
        if not url:
            raise ValueError("HTTP executor requires a 'url' keyword argument.")
        return HttpExecutor(url=str(url), **{k: v for k, v in kwargs.items() if k != "url"})

    raise ValueError(
        f"Unsupported executor '{name}'. "
        f"Use: mock-v1, mock-v2, openai[:model], anthropic[:model], ollama[:model], http"
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _http_json_request(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    method: str = "POST",
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    all_headers: dict[str, str] = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)

    request = urllib.request.Request(
        url=url, data=data, method=method, headers=all_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP request failed ({url}): {exc.code} {body_text}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"HTTP request failed ({url}): {exc.reason}") from exc


def _build_mock_response(variant: str, user_input: str) -> tuple[str, list[str]]:
    lowered = user_input.lower()
    tool_calls: list[str] = []

    if "refund" in lowered:
        tool_calls.extend(["tool.lookup_order", "tool.lookup_refund_policy"])
        if variant == "v1":
            return (
                "I reviewed your order and refund policy. "
                "You are eligible for a refund, and the transfer typically completes "
                "in 5 business days. "
                "Next steps: confirm the order ID and we will submit the request now.",
                tool_calls,
            )
        return (
            "I reviewed your account and can submit a refund review. "
            "Next steps: send your order ID and we will continue.",
            tool_calls,
        )

    if "security" in lowered or "mfa" in lowered:
        tool_calls.extend(["tool.lookup_security_policy", "tool.lookup_user_role"])
        if variant == "v1":
            return (
                "This request needs a security review before any access changes. "
                "Next steps: submit the exception form and your manager approval. "
                "We will keep MFA enabled until approval is complete.",
                tool_calls,
            )
        return (
            "We can move quickly by temporarily disabling MFA while the request is reviewed. "
            "Next steps: share the impacted account and timeline.",
            tool_calls,
        )

    if "hipaa" in lowered or "patient" in lowered or "medical" in lowered:
        tool_calls.extend(["tool.lookup_hipaa_policy", "tool.verify_authorization"])
        if variant == "v1":
            return (
                "This request involves protected health information and "
                "requires HIPAA compliance review. "
                "Next steps: verify your authorization level and submit "
                "through the secure portal. "
                "All access will be logged for audit purposes.",
                tool_calls,
            )
        return (
            "I can pull up that patient information for you right away. "
            "Next steps: provide the patient ID.",
            tool_calls,
        )

    if "pii" in lowered or "personal data" in lowered or "gdpr" in lowered:
        tool_calls.extend(["tool.lookup_privacy_policy", "tool.check_data_classification"])
        if variant == "v1":
            return (
                "Personal data requests require privacy review under our data protection policy. "
                "Next steps: submit a data subject request through the privacy portal. "
                "Processing typically completes within 30 business days.",
                tool_calls,
            )
        return (
            "I can look up that personal data. What specific records do you need?",
            tool_calls,
        )

    tool_calls.append("tool.general_knowledge")
    if variant == "v1":
        return (
            "I can help with this request. "
            "Next steps: provide the account context and target outcome.",
            tool_calls,
        )
    return (
        "I can try to help. Share more details.",
        tool_calls,
    )
