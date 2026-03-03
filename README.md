# ContractOps

**CI-grade behavior contracts, baseline replay, and release gates for AI agents.**

ContractOps treats agent behavior like code quality: you define expected outcomes, capture a baseline, and gate releases when behavior drifts. It plugs directly into CI/CD pipelines to prevent silent regressions from model upgrades, prompt changes, or orchestration edits.

---

## GitHub Pages Brand Site

A production-ready brand + documentation site lives in `docs/` and includes:

- polished positioning and value proposition,
- benchmark visualizations,
- implementation documentation and quickstart,
- roadmap and future status tracking.

### Preview locally

```bash
python -m http.server 8000 --directory docs
```

Then open `http://localhost:8000`.

### Publish to `<org-or-user>.github.io`

1. Push this repository to GitHub.
2. Ensure your default branch is `main`.
3. In repository settings, open **Pages** and set **Build and deployment** to **GitHub Actions**.
4. The included workflow (`.github/workflows/pages.yml`) deploys `docs/` automatically on push.

### Publish as `contractops.github.io` (no username path)

To get the exact root URL `https://contractops.github.io/`, GitHub requires:

1. GitHub owner/account/org name: `contractops`
2. Repository name: `contractops.github.io`

If those naming rules are not met, GitHub Pages will publish as a project site under a user/org path instead.

### CNAME custom domain setup

The site now includes `docs/CNAME` and is currently set to `contractops.github.io`.
Update that file to your real external domain when ready (for example `www.contractops.ai`) and point DNS to GitHub Pages.

## Why This Exists

Most AI platforms provide one slice of reliability -- observability, evals, or guardrails. Teams still lack a practical **change control** layer that combines:

- **Behavior contracts**: hard checks on required phrases, forbidden outputs, regex patterns, tool call verification, latency limits, JSON schema validation, semantic similarity, LLM-as-a-judge, and policy violation detection
- **Baseline replay**: capture known-good behavior and compare via string diff or **embedding-based semantic similarity**
- **Multi-trial stability**: run scenarios N times to detect flaky/non-deterministic behavior with pass@k metrics
- **Release scoring**: a single score combining contract pass rate and behavior similarity
- **Policy packs**: pre-built compliance suites for OWASP AI, PII/GDPR, HIPAA, financial services, and enterprise safety
- **Orchestration adapters**: native integration with LangGraph, CrewAI, and generic trace-based agent frameworks
- **Enterprise governance**: scenario registries, approval workflows, audit trails, and notifications
- **CI/CD gating**: pass/fail exit codes, JUnit XML, GitHub PR comments

## Quick Start

### Install

```bash
pip install -e .
```

### Initialize a project

```bash
contractops init
```

This creates `contractops.yaml`, a `scenarios/` directory, and `.contractops/baselines/`.

### Capture a baseline

```bash
contractops baseline --scenario examples/customer_refund.json --executor mock-v1
```

### Run a check

```bash
contractops check --scenario examples/customer_refund.json --executor mock-v2
```

The check will fail with clear reasons, demonstrating contract + drift gates.

### Run an entire scenario suite

```bash
contractops run --scenarios examples/ --executor mock-v1 --format json
```

### Run with multi-trial stability testing

```bash
contractops run --scenarios examples/ --executor ollama:llama3.1:8b --trials 5 --pass-threshold 0.8
```

### Run with semantic similarity

```bash
contractops run --scenarios examples/ --executor ollama:llama3.1:8b --semantic --embed-model llama3.1:8b
```

### Run a policy pack

```bash
contractops packs list
contractops packs run owasp --executor ollama:llama3.1:8b
contractops packs export hipaa --output-dir scenarios/
```

### Manage baseline lifecycle

```bash
contractops lifecycle approve --scenario-id customer-refund-enterprise --approver admin
contractops lifecycle status --scenario-id customer-refund-enterprise
contractops lifecycle history --scenario-id customer-refund-enterprise
contractops lifecycle expire --scenario-id customer-refund-enterprise --reason "Model upgrade"
```

### Validate scenarios

```bash
contractops validate examples/
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize a ContractOps project with config, dirs, and example scenario |
| `baseline` | Capture and save a baseline run for a scenario |
| `check` | Run contracts and compare to baseline for a single scenario |
| `run` | Batch-run all scenarios with aggregated reporting, multi-trial, semantic |
| `validate` | Validate scenario files for correctness |
| `packs list` | List available policy packs |
| `packs run <pack>` | Run a policy pack against an executor |
| `packs export <pack>` | Export a pack as scenario files |
| `lifecycle approve` | Approve a baseline for release gating |
| `lifecycle expire` | Expire a baseline |
| `lifecycle status` | Show lifecycle status of a baseline |
| `lifecycle history` | Show baseline version history |

### Common Options

```
--executor       Executor backend (mock-v1, mock-v2, openai[:model], anthropic[:model], ollama[:model], http)
--baseline-dir   Baseline storage directory
--min-similarity Minimum similarity threshold (0.0-1.0)
--min-score      Minimum release score (0-100)
--require-baseline  Fail if no baseline exists
--env            Threshold profile from config (default, staging, production)
--format         Output format: markdown, json, junit, github
--output         Write report to file
--tags           Comma-separated tags to filter scenarios
--parallel       Number of parallel workers for batch runs
--trials         Number of trials per scenario for stability testing
--pass-threshold Required trial pass rate (0.0-1.0)
--semantic       Use embedding-based semantic similarity
--embed-model    Ollama model for embeddings (default: llama3.1:8b)
--embed-url      Ollama base URL for embeddings
```

## Scenario Format

Scenarios are JSON or YAML files that define an input, expected behavior contracts, and metadata:

```json
{
  "id": "customer-refund-enterprise",
  "description": "Support agent handles a refund request.",
  "input": "I am an enterprise customer requesting a refund...",
  "tags": ["support", "refund"],
  "expected": {
    "must_include": ["refund", "next steps", "business days"],
    "must_not_include": ["cannot help", "legal advice"],
    "regex": ["[0-9]{1,2}\\s+business\\s+days"],
    "max_chars": 600,
    "min_chars": 50,
    "max_latency_ms": 5000,
    "required_tools": ["tool.lookup_order", "tool.lookup_refund_policy"],
    "json_schema": {},
    "sentiment_positive": true,
    "semantic_match": [
      {
        "reference": "I will process your refund within five business days.",
        "threshold": 0.8,
        "model": "llama3.1:8b"
      }
    ],
    "llm_judge": [
      {
        "rubric": "The response should be helpful, professional, and include next steps.",
        "threshold": 0.7,
        "model": "llama3.1:8b"
      }
    ],
    "policy_violation": ["pii_leak", "prompt_injection", "unauthorized_action"]
  },
  "metadata": {
    "domain": "support",
    "criticality": "high"
  }
}
```

### Contract Types

| Contract | Description |
|----------|-------------|
| `must_include` | Case-insensitive phrase that must appear in output |
| `must_not_include` | Case-insensitive phrase that must NOT appear |
| `regex` | Regex pattern that must match (case-insensitive) |
| `max_chars` | Maximum output character count |
| `min_chars` | Minimum output character count |
| `max_latency_ms` | Maximum execution latency in milliseconds |
| `required_tools` | Tool calls that must appear in the run result |
| `json_schema` | JSON Schema the output must validate against |
| `sentiment_positive` | Heuristic check that output tone is positive/helpful |
| `semantic_match` | Embedding-based cosine similarity against a reference text |
| `llm_judge` | LLM-as-a-judge evaluation against a rubric |
| `policy_violation` | Pattern-based policy violation detection (builtin + custom) |

### Builtin Policies

| Policy | Description |
|--------|-------------|
| `pii_leak` | Detects SSN, credit card, email, phone patterns |
| `prompt_injection` | Detects prompt injection leaking through |
| `unauthorized_action` | Detects unsafe authorization bypasses |
| `financial_advice` | Detects inappropriate financial recommendations |
| `medical_diagnosis` | Detects inappropriate medical claims |

### Policy Packs

| Pack | Scenarios | Domain |
|------|-----------|--------|
| `owasp` | 5 | AI security (OWASP Top-10) |
| `pii-gdpr` | 3 | PII protection and GDPR compliance |
| `hipaa` | 3 | Healthcare and PHI protection |
| `financial` | 3 | Financial services compliance |
| `enterprise-safety` | 3 | General enterprise safety |

## Configuration

Project-level configuration via `contractops.yaml`:

```yaml
scenarios_dir: scenarios
default_executor: mock-v1
baseline_executor: mock-v1

storage:
  backend: local                    # local, s3, gcs
  base_path: .contractops/baselines
  # bucket: my-bucket              # for s3/gcs
  # prefix: contractops/baselines  # for s3/gcs
  # region: us-east-1              # for s3

thresholds:
  default:
    min_similarity: 0.85
    min_score: 80
    require_baseline: false
  staging:
    min_similarity: 0.80
    min_score: 75
    require_baseline: true
  production:
    min_similarity: 0.90
    min_score: 85
    require_baseline: true

output_format: markdown
```

Use `--env staging` or `--env production` to apply the corresponding thresholds.

## Executors

| Executor | Description |
|----------|-------------|
| `mock-v1` | Deterministic compliant responses for testing |
| `mock-v2` | Deterministic non-compliant responses (triggers failures) |
| `openai[:model]` | OpenAI-compatible API (requires `OPENAI_API_KEY`) |
| `anthropic[:model]` | Anthropic Messages API (requires `ANTHROPIC_API_KEY`) |
| `ollama[:model]` | Local Ollama models (default: llama3.1:8b) |
| `http` | Generic HTTP/webhook executor for any agent API |
| `langchain` | Wraps any LangChain Runnable (programmatic use) |

### Orchestration Adapters (Programmatic)

| Adapter | Framework | Description |
|---------|-----------|-------------|
| `LangGraphExecutor` | LangGraph | Wraps compiled StateGraph |
| `CrewAIExecutor` | CrewAI | Wraps Crew with task extraction |
| `TraceExecutor` | Generic | Wraps any callable returning traces |

## Storage Backends

| Backend | Install | Description |
|---------|---------|-------------|
| `local` | (included) | Local filesystem storage |
| `s3` | `pip install contractops[s3]` | AWS S3 baseline storage |
| `gcs` | `pip install contractops[gcs]` | Google Cloud Storage |

## Output Formats

| Format | Use Case |
|--------|----------|
| `markdown` | Human-readable terminal output |
| `json` | Machine-readable for CI pipelines |
| `junit` | JUnit XML for Jenkins, GitHub Actions, etc. |
| `github` | Collapsible PR comment with pass/fail summary |

## Enterprise Features

### Scenario Registry

Centralized, versioned scenario management with tagging, search, and cross-repo import/export.

```python
from contractops.registry import ScenarioRegistry

registry = ScenarioRegistry(".contractops/registry")
registry.register(scenario, author="team-lead")
registry.search("refund")
registry.export_pack("shared/", tags=["security"])
```

### Audit Trail

Append-only, hash-chained audit log for governance compliance. Every gate decision, baseline save, approval, and expiration is recorded with cryptographic integrity.

```python
from contractops.audit import AuditLog

audit = AuditLog(".contractops/audit")
audit.record_gate_decision("scenario-1", passed=True, score=92, executor="v1", reasons=[])
is_valid, errors = audit.verify_integrity()
audit.export_csv("compliance_report.csv")
```

### Notifications

Fire-and-forget notifications for failed gates and lifecycle events via Slack, Teams, Jira, or generic webhooks.

```python
from contractops.notifications import NotificationManager, SlackWebhook

mgr = NotificationManager()
mgr.add_hook(SlackWebhook("https://hooks.slack.com/...", channel="#alerts"))
mgr.notify_gate_result(suite_result, context="PR #123")
```

### Dashboard Analytics

Executive KPIs, scenario risk scoring, drift hotspot detection, and reliability trend analysis.

```python
from contractops.dashboard import DashboardAnalytics

analytics = DashboardAnalytics(audit_log)
summary = analytics.executive_summary()
risks = analytics.scenario_risk_scores()
trend = analytics.reliability_trend(window_size=10)
```

### RBAC & Tenant Isolation

Role-based access control with API key authentication and multi-tenant boundaries.

```python
from contractops.auth import AuthManager

auth = AuthManager()
user = auth.create_user("dev1", email="dev@co.com", role="developer", tenant_id="team-a")
api_key = auth.generate_api_key("dev1")
authenticated = auth.authenticate_key(api_key)
```

### Policy-as-Code

Centralized governance policies with repo-level overrides within guardrails.

```python
from contractops.policy_code import PolicyManager, PolicyDefinition, PolicySet

mgr = PolicyManager()
central = PolicySet("central")
central.add(PolicyDefinition(
    name="no-pii", severity="error",
    assertions={"policy_violation": ["pii_leak"]},
    overridable=False,
))
mgr.save_central(central)
```

## GitHub Action

Use ContractOps directly in GitHub Actions:

```yaml
- name: Run ContractOps
  uses: ./.github
  with:
    command: run
    scenarios: examples/
    executor: openai:gpt-4o-mini
    format: github
    post-pr-comment: "true"
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Programmatic Usage

```python
from contractops.scenario import load_scenario, load_scenarios_from_dir
from contractops.executors import build_executor
from contractops.assertions import evaluate_contracts
from contractops.baseline import save_baseline, load_baseline, compare_outputs
from contractops.storage import LocalStorage
from contractops.suite import run_suite
from contractops.report import build_release_report, render_markdown

# Single scenario
scenario = load_scenario("examples/customer_refund.json")
executor = build_executor("mock-v1")
result = executor.run(scenario)
evaluation = evaluate_contracts(scenario, result)
print(f"Passed: {evaluation.passed}, Rate: {evaluation.pass_rate:.0%}")

# Batch suite with multi-trial
scenarios = load_scenarios_from_dir("examples/", tags=["support"])
storage = LocalStorage(".contractops/baselines")
suite_result = run_suite(
    scenarios, executor, storage=storage,
    parallel=4, trials=3, pass_threshold=0.8,
    use_semantic=True, embed_model="llama3.1:8b",
)
print(f"Suite: {suite_result.passed_count}/{suite_result.total} passed")
print(f"Flaky: {suite_result.flaky_count}")

# LangGraph integration
from contractops.adapters import LangGraphExecutor
# lg_executor = LangGraphExecutor(compiled_graph, name="my-agent")
# result = lg_executor.run(scenario)

# Policy pack execution
from contractops.policy_packs import load_pack_scenarios
owasp_scenarios = load_pack_scenarios("owasp")
result = run_suite(owasp_scenarios, executor)
```

## Release Scoring

The release score combines hard contract checks and behavioral similarity:

```
score = (contract_pass_rate * 70) + (similarity_to_baseline * 30)
```

A run passes only when:
1. All hard contract checks pass
2. Behavior similarity is within drift tolerance (if baseline exists)
3. Combined release score meets the threshold

## Project Structure

```
contractops/
  __init__.py         Package root (v0.3.0)
  models.py           Data models (Scenario, RunResult, StabilityMetrics, etc.)
  config.py           YAML/JSON config loading with threshold profiles
  scenario.py         Scenario loading (JSON/YAML), directory scanning, tag filtering
  executors.py        Execution backends (mock, OpenAI, Anthropic, Ollama, LangChain, HTTP)
  assertions.py       Contract evaluation engine (15+ check types)
  embeddings.py       Embedding-based semantic similarity via Ollama
  storage.py          Pluggable storage (local, S3, GCS)
  baseline.py         Baseline capture, persistence, semantic + string diff comparison
  suite.py            Batch runner with multi-trial stability and parallel execution
  report.py           Multi-format reporting with stability columns
  github.py           GitHub API integration (PR comments, commit statuses)
  cli.py              CLI entry point with packs + lifecycle commands
  policy_packs.py     Pre-built compliance suites (OWASP, GDPR, HIPAA, financial)
  adapters.py         Orchestration adapters (LangGraph, CrewAI, generic traces)
  lifecycle.py        Baseline lifecycle (approve, expire, rotate, versioning)
  registry.py         Scenario registry (versioned, tagged, searchable, import/export)
  audit.py            Hash-chained audit trail with JSON/CSV export
  notifications.py    Notification hooks (Slack, Teams, Jira, generic webhook)
  dashboard.py        Analytics: risk scores, drift hotspots, reliability trends, KPIs
  auth.py             RBAC, API key management, tenant isolation
  policy_code.py      Policy-as-code with central governance and repo overrides
tests/                293 tests (all pass), covering every module
examples/             Real-world scenario contracts
benchmarks/           LLM benchmark results across 7 models
.github/
  action.yml          Reusable GitHub Action
  workflows/ci.yml    CI pipeline for this project
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v          # 293 tests
ruff check contractops/ tests/
mypy contractops/ --ignore-missing-imports
```

## License

MIT
