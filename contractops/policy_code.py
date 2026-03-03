"""Policy-as-code management: centralized governance with repo-level overrides.

Enables organizations to define baseline policies centrally and allow
individual repos/teams to apply overrides within guardrails.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("contractops.policy_code")


class PolicyDefinition:
    """A single policy definition with constraints and assertion rules."""

    def __init__(
        self,
        name: str,
        description: str = "",
        severity: str = "error",
        assertions: dict[str, Any] | None = None,
        applies_to: list[str] | None = None,
        overridable: bool = True,
    ) -> None:
        self.name = name
        self.description = description
        self.severity = severity
        self.assertions = assertions or {}
        self.applies_to = applies_to or []
        self.overridable = overridable

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "severity": self.severity,
            "assertions": self.assertions,
            "applies_to": self.applies_to,
            "overridable": self.overridable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyDefinition:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            severity=data.get("severity", "error"),
            assertions=data.get("assertions", {}),
            applies_to=data.get("applies_to", []),
            overridable=data.get("overridable", True),
        )


class PolicySet:
    """A collection of policies that can be applied to scenarios."""

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self.policies: dict[str, PolicyDefinition] = {}

    def add(self, policy: PolicyDefinition) -> None:
        self.policies[policy.name] = policy

    def remove(self, policy_name: str) -> bool:
        if policy_name in self.policies:
            del self.policies[policy_name]
            return True
        return False

    def get(self, policy_name: str) -> PolicyDefinition | None:
        return self.policies.get(policy_name)

    def list_policies(self, severity: str = "") -> list[PolicyDefinition]:
        policies = list(self.policies.values())
        if severity:
            policies = [p for p in policies if p.severity == severity]
        return sorted(policies, key=lambda p: p.name)

    def merge_assertions_for_scenario(
        self, scenario_tags: list[str]
    ) -> dict[str, Any]:
        """Combine all applicable policy assertions for a scenario."""
        merged: dict[str, Any] = {}
        for policy in self.policies.values():
            if not policy.applies_to or _tags_overlap(policy.applies_to, scenario_tags):
                for key, value in policy.assertions.items():
                    if key in merged:
                        if isinstance(merged[key], list) and isinstance(value, list):
                            merged[key] = list(set(merged[key]) | set(value))
                        elif isinstance(merged[key], list):
                            merged[key].append(value)
                        else:
                            merged[key] = value
                    else:
                        merged[key] = value
        return merged

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "policies": {k: v.to_dict() for k, v in self.policies.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicySet:
        ps = cls(name=data.get("name", "default"))
        for name, policy_data in data.get("policies", {}).items():
            policy_data["name"] = name
            ps.add(PolicyDefinition.from_dict(policy_data))
        return ps


class PolicyManager:
    """Manages central policies with repo-level overrides."""

    def __init__(self, policy_dir: str = ".contractops/policies") -> None:
        self._dir = Path(policy_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._central: PolicySet | None = None
        self._overrides: PolicySet | None = None

    def load_central(self, path: str | Path | None = None) -> PolicySet:
        """Load the central (organization-level) policy set."""
        if path is None:
            path = self._dir / "central.yaml"
        self._central = self._load_policy_file(Path(path))
        return self._central

    def load_overrides(self, path: str | Path | None = None) -> PolicySet:
        """Load repo-level policy overrides."""
        if path is None:
            path = self._dir / "overrides.yaml"
        self._overrides = self._load_policy_file(Path(path))
        return self._overrides

    def effective_policies(self) -> PolicySet:
        """Compute the effective policy set (central + allowed overrides)."""
        if self._central is None:
            self._central = PolicySet("central")
        effective = PolicySet("effective")

        for name, policy in self._central.policies.items():
            effective.add(policy)

        if self._overrides:
            for name, override in self._overrides.policies.items():
                central_policy = self._central.get(name)
                if central_policy is not None and not central_policy.overridable:
                    logger.warning(
                        "Policy '%s' is not overridable; skipping override", name
                    )
                    continue
                effective.add(override)

        return effective

    def save_central(self, policy_set: PolicySet) -> str:
        path = self._dir / "central.yaml"
        self._save_policy_file(path, policy_set)
        self._central = policy_set
        return str(path)

    def save_overrides(self, policy_set: PolicySet) -> str:
        path = self._dir / "overrides.yaml"
        self._save_policy_file(path, policy_set)
        self._overrides = policy_set
        return str(path)

    def validate_overrides(self) -> list[str]:
        """Check that overrides don't violate central policy constraints."""
        errors: list[str] = []
        if self._central is None or self._overrides is None:
            return errors

        for name, override in self._overrides.policies.items():
            central = self._central.get(name)
            if central is not None and not central.overridable:
                errors.append(f"Policy '{name}' cannot be overridden (locked by central).")

        return errors

    def _load_policy_file(self, path: Path) -> PolicySet:
        if not path.exists():
            return PolicySet()
        raw_text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            data = json.loads(raw_text)
        else:
            data = yaml.safe_load(raw_text) or {}
        return PolicySet.from_dict(data)

    def _save_policy_file(self, path: Path, policy_set: PolicySet) -> None:
        data = policy_set.to_dict()
        if path.suffix == ".json":
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        else:
            path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")


def _tags_overlap(policy_tags: list[str], scenario_tags: list[str]) -> bool:
    return bool(set(policy_tags) & set(scenario_tags))
