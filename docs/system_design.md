# System Design

## Design Goal

Provide deterministic, explainable release gating for AI agent behavior.

## Current MVP Architecture

```text
Scenario JSON
    |
    v
Executor (mock/openai-compatible)
    |
    v
RunResult (output, latency, tool calls)
    |
    +--> Contract Assertions (hard checks)
    |
    +--> Baseline Comparison (similarity + diff)
    |
    v
Release Report (score + pass/fail reasons)
```

## Key Components

### 1) Scenario Loader

- File: `contractops/scenario.py`
- Responsibility:
  - load scenario JSON,
  - enforce required fields.

### 2) Executors

- File: `contractops/executors.py`
- Responsibility:
  - run a scenario via configured backend.
- Current adapters:
  - `mock-v1`, `mock-v2` for deterministic demos,
  - `openai[:model]` for real provider calls.

### 3) Assertion Engine

- File: `contractops/assertions.py`
- Supported checks:
  - `must_include`,
  - `must_not_include`,
  - `regex`,
  - `max_chars`,
  - `required_tools`.

### 4) Baseline Store + Comparison

- File: `contractops/baseline.py`
- Responsibility:
  - persist baseline run artifacts,
  - compare candidate output to baseline,
  - produce similarity and diff preview.

### 5) Decision + Reporting

- File: `contractops/report.py`
- Responsibility:
  - compute release score,
  - apply thresholds,
  - emit explainable pass/fail report.

### 6) CLI

- File: `contractops/cli.py`
- Commands:
  - `baseline`
  - `check`

## Reliability Model

A run should pass only when:
1. all hard contract checks pass,
2. behavior similarity is within drift tolerance (if baseline exists),
3. combined release score meets threshold.

This avoids both false confidence (only using similarity) and brittle strictness (only using phrase checks).

## Scale Roadmap

### Storage and Data Model

- Move from local files to object storage and metadata DB.
- Keep immutable run artifacts for auditability.

### Framework Adapters

- Add native adapters for:
  - LangGraph run traces,
  - CrewAI task/agent traces,
  - custom event streams.

### CI/CD Integrations

- GitHub/GitLab plugins:
  - post PR comments with failed contracts,
  - enforce reliability budgets,
  - require approval for high-risk drift.

### Security and Compliance

- Encrypt run payloads at rest.
- Redact sensitive fields from scenario/run logs.
- Add audit reports for policy and release decisions.

## Non-Goals (for MVP)

- Not a full observability suite.
- Not a full LLM evaluation science platform.
- Not a guardrail enforcement runtime.

The wedge is release governance and change safety.
