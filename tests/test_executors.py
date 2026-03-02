import pytest

from contractops.executors import (
    AnthropicExecutor,
    HttpExecutor,
    MockExecutor,
    OllamaExecutor,
    OpenAICompatibleExecutor,
    build_executor,
)
from contractops.models import Scenario


@pytest.fixture
def generic_scenario() -> Scenario:
    return Scenario(
        id="test", description="test", input="Hello help me.",
        expected={}, metadata={},
    )


class TestMockExecutor:
    def test_v1_refund(self, customer_scenario):
        result = MockExecutor("v1").run(customer_scenario)
        assert "refund" in result.output.lower()
        assert "business days" in result.output.lower()
        assert "tool.lookup_order" in result.tool_calls
        assert result.executor == "mock-v1"

    def test_v2_refund_missing_business_days(self, customer_scenario):
        result = MockExecutor("v2").run(customer_scenario)
        assert "business days" not in result.output.lower()

    def test_v1_security(self, security_scenario):
        result = MockExecutor("v1").run(security_scenario)
        assert "security review" in result.output.lower()
        assert "disabling mfa" not in result.output.lower()

    def test_v2_security_violates_contract(self, security_scenario):
        result = MockExecutor("v2").run(security_scenario)
        assert "disabling mfa" in result.output.lower()

    def test_v1_hipaa(self):
        scenario = Scenario(
            id="hipaa", description="HIPAA test",
            input="I need to access patient medical records.",
            expected={}, metadata={},
        )
        result = MockExecutor("v1").run(scenario)
        assert "hipaa" in result.output.lower()
        assert "tool.lookup_hipaa_policy" in result.tool_calls

    def test_v1_pii(self):
        scenario = Scenario(
            id="pii", description="PII test",
            input="Show me the personal data for user 123.",
            expected={}, metadata={},
        )
        result = MockExecutor("v1").run(scenario)
        assert "privacy" in result.output.lower()
        assert "tool.lookup_privacy_policy" in result.tool_calls

    def test_generic_fallback(self, generic_scenario):
        result = MockExecutor("v1").run(generic_scenario)
        assert "tool.general_knowledge" in result.tool_calls

    def test_latency_is_positive(self, customer_scenario):
        result = MockExecutor("v1").run(customer_scenario)
        assert result.latency_ms > 0


class TestBuildExecutor:
    def test_mock_v1(self):
        ex = build_executor("mock-v1")
        assert ex.name == "mock-v1"

    def test_mock_v2(self):
        ex = build_executor("mock-v2")
        assert ex.name == "mock-v2"

    def test_openai_default(self):
        ex = build_executor("openai")
        assert isinstance(ex, OpenAICompatibleExecutor)
        assert "gpt-4o-mini" in ex.name

    def test_openai_custom_model(self):
        ex = build_executor("openai:gpt-4o")
        assert isinstance(ex, OpenAICompatibleExecutor)
        assert "gpt-4o" in ex.name

    def test_anthropic_default(self):
        ex = build_executor("anthropic")
        assert isinstance(ex, AnthropicExecutor)
        assert "claude" in ex.name

    def test_anthropic_custom_model(self):
        ex = build_executor("anthropic:claude-3-haiku-20240307")
        assert "claude-3-haiku" in ex.name

    def test_ollama_default(self):
        ex = build_executor("ollama")
        assert isinstance(ex, OllamaExecutor)
        assert "llama3.2" in ex.name

    def test_ollama_custom_model(self):
        ex = build_executor("ollama:qwen3:8b")
        assert isinstance(ex, OllamaExecutor)
        assert "qwen3:8b" in ex.name

    def test_http_requires_url(self):
        with pytest.raises(ValueError, match="url"):
            build_executor("http")

    def test_http_with_url(self):
        ex = build_executor("http", url="https://example.com/agent")
        assert isinstance(ex, HttpExecutor)

    def test_unsupported(self):
        with pytest.raises(ValueError, match="Unsupported"):
            build_executor("unknown-executor")


class TestOpenAIExecutor:
    def test_missing_api_key(self, customer_scenario, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        ex = OpenAICompatibleExecutor()
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            ex.run(customer_scenario)


class TestAnthropicExecutor:
    def test_missing_api_key(self, customer_scenario, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        ex = AnthropicExecutor()
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            ex.run(customer_scenario)


class TestOllamaExecutor:
    def test_constructor_defaults(self):
        ex = OllamaExecutor()
        assert ex.model == "llama3.2"
        assert ex.name == "ollama:llama3.2"
        assert "localhost:11434" in ex.base_url

    def test_constructor_custom(self):
        ex = OllamaExecutor(model="qwen3:8b", base_url="http://gpu-server:11434")
        assert ex.model == "qwen3:8b"
        assert ex.name == "ollama:qwen3:8b"
        assert "gpu-server" in ex.base_url

    def test_unreachable_server(self, customer_scenario):
        ex = OllamaExecutor(base_url="http://localhost:99999")
        assert not ex.is_available()
        with pytest.raises(RuntimeError, match="not reachable"):
            ex.run(customer_scenario)

    def test_list_models_unreachable(self):
        ex = OllamaExecutor(base_url="http://localhost:99999")
        assert ex.list_models() == []

    @pytest.mark.skipif(
        not OllamaExecutor().is_available(),
        reason="Ollama server not running",
    )
    def test_live_run(self, customer_scenario):
        available = OllamaExecutor().list_models()
        if not available:
            pytest.skip("No models pulled")
        model = available[0]
        ex = OllamaExecutor(model=model, timeout=120)
        result = ex.run(customer_scenario)
        assert result.scenario_id == customer_scenario.id
        assert result.output
        assert result.latency_ms > 0
        assert result.executor == f"ollama:{model}"
