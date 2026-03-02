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

- **Behavior contracts**: hard checks on required phrases, forbidden outputs, regex patterns, tool call verification, latency limits, JSON schema validation
- **Baseline replay**: capture known-good behavior and compare every candidate against it
- **Release scoring**: a single score combining contract pass rate and behavior similarity
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
| `run` | Batch-run all scenarios in a directory with aggregated reporting |
| `validate` | Validate scenario files for correctness |

### Common Options

```
--executor       Executor backend (mock-v1, mock-v2, openai[:model], anthropic[:model], http)
--baseline-dir   Baseline storage directory
--min-similarity Minimum similarity threshold (0.0-1.0)
--min-score      Minimum release score (0-100)
--require-baseline  Fail if no baseline exists
--env            Threshold profile from config (default, staging, production)
--format         Output format: markdown, json, junit, github
--output         Write report to file
--tags           Comma-separated tags to filter scenarios
--parallel       Number of parallel workers for batch runs
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
    "sentiment_positive": true
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
| `http` | Generic HTTP/webhook executor for any agent API |
| `langchain` | Wraps any LangChain Runnable (programmatic use) |

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

### Action Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `command` | `run` | baseline, check, or run |
| `scenarios` | (required) | Path to scenario file or directory |
| `executor` | config default | Executor backend |
| `min-similarity` | `0.85` | Similarity threshold |
| `min-score` | `80` | Score threshold |
| `require-baseline` | `false` | Fail if no baseline |
| `format` | `github` | Output format |
| `post-pr-comment` | `true` | Post results as PR comment |

### Action Outputs

| Output | Description |
|--------|-------------|
| `passed` | `true` or `false` |
| `score` | Overall release score |
| `report` | Full report text |

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

# Batch suite
scenarios = load_scenarios_from_dir("examples/", tags=["support"])
storage = LocalStorage(".contractops/baselines")
suite_result = run_suite(scenarios, executor, storage=storage, parallel=4)
print(f"Suite: {suite_result.passed_count}/{suite_result.total} passed")

# LangChain integration
from contractops.executors import LangChainExecutor
# lc_executor = LangChainExecutor(your_chain, name="my-agent")
# result = lc_executor.run(scenario)
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
  __init__.py         Package root
  models.py           Data models (Scenario, RunResult, SuiteResult, etc.)
  config.py           YAML/JSON config loading with threshold profiles
  scenario.py         Scenario loading (JSON/YAML), directory scanning, tag filtering
  executors.py        Execution backends (mock, OpenAI, Anthropic, LangChain, HTTP)
  assertions.py       Contract evaluation engine (10+ check types)
  storage.py          Pluggable storage (local, S3, GCS)
  baseline.py         Baseline capture, persistence, and diff comparison
  suite.py            Batch scenario runner with parallel execution
  report.py           Multi-format reporting (Markdown, JSON, JUnit XML, GitHub)
  github.py           GitHub API integration (PR comments, commit statuses)
  cli.py              CLI entry point (init, baseline, check, run, validate)
tests/                Comprehensive pytest test suite
examples/             Real-world scenario contracts
.github/
  action.yml          Reusable GitHub Action
  workflows/ci.yml    CI pipeline for this project
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check contractops/ tests/
mypy contractops/ --ignore-missing-imports
```

## License

MIT
