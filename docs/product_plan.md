# Product Plan

## Product Vision

Become the reliability layer that decides whether an AI agent change can ship.

## Ideal Customer Profile (ICP)

Primary:
- Mid-market to enterprise product teams shipping internal or customer-facing AI agents.
- 5-50 engineers touching prompts/models/orchestration.
- Regulated or high-trust domains (finance, healthcare ops, security, enterprise support).

Secondary:
- AI consultancies and system integrators deploying many agent workflows.

## Problem Statement

"We can observe and evaluate AI behavior, but we still cannot reliably approve changes before production."

## Value Proposition

ContractOps helps teams:
- catch behavior regressions before deployment,
- quantify release risk with objective scores,
- standardize governance across multiple frameworks/providers.

## MVP Scope (Implemented in this repo)

1. Scenario contracts in JSON
2. Baseline capture
3. Candidate check with:
   - hard contract assertions
   - baseline similarity
   - release scoring and pass/fail
4. CLI-friendly output for CI integration

## 90-Day Build Plan

### Phase 1: Developer Wedge
- CLI + local runner (done in MVP)
- GitHub Action template
- Baseline artifact storage support (S3/GCS/local)

### Phase 2: Team Adoption
- Scenario registry and tagging
- Threshold profiles by environment (dev/staging/prod)
- Slack/Jira notifications for failed gates

### Phase 3: Enterprise Motion
- SSO, RBAC, audit trails
- Policy packs (security, legal-safe response behaviors)
- Reliability dashboards by team/model/version

## Commercialization Strategy

- Open-core developer entry point.
- Paid cloud features:
  - team governance,
  - policy management,
  - audit and compliance reporting,
  - high-scale run history and analytics.

## Acquisition Signals to Target

1. Strong overlap with orchestrator ecosystems (LangGraph/CrewAI users).
2. Demonstrated reduction in model-upgrade incident rates.
3. Tight integrations with provider APIs and enterprise controls.
4. "Must-have" position in enterprise procurement conversations.

## Success Metrics

Product:
- % of releases gated by contracts
- regression catch rate pre-prod
- median time-to-approve model updates

Business:
- expansion within existing engineering orgs
- number of critical workflows onboarded
- annual retention in regulated accounts
