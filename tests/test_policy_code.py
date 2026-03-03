"""Tests for policy-as-code management."""

from __future__ import annotations

from pathlib import Path

from contractops.policy_code import PolicyDefinition, PolicyManager, PolicySet


class TestPolicyDefinition:
    def test_roundtrip(self) -> None:
        policy = PolicyDefinition(
            name="no-pii",
            description="Prevent PII leaks",
            severity="error",
            assertions={"policy_violation": ["pii_leak"]},
            applies_to=["support", "finance"],
            overridable=False,
        )
        d = policy.to_dict()
        restored = PolicyDefinition.from_dict(d)
        assert restored.name == "no-pii"
        assert restored.overridable is False
        assert "pii_leak" in restored.assertions["policy_violation"]


class TestPolicySet:
    def test_add_and_get(self) -> None:
        ps = PolicySet("test")
        ps.add(PolicyDefinition(name="p1", severity="error"))
        ps.add(PolicyDefinition(name="p2", severity="warning"))

        assert ps.get("p1") is not None
        assert ps.get("nonexistent") is None

    def test_list_policies(self) -> None:
        ps = PolicySet()
        ps.add(PolicyDefinition(name="a", severity="error"))
        ps.add(PolicyDefinition(name="b", severity="warning"))
        ps.add(PolicyDefinition(name="c", severity="error"))

        all_policies = ps.list_policies()
        assert len(all_policies) == 3

        errors = ps.list_policies(severity="error")
        assert len(errors) == 2

    def test_remove(self) -> None:
        ps = PolicySet()
        ps.add(PolicyDefinition(name="removable"))
        assert ps.remove("removable")
        assert ps.get("removable") is None
        assert not ps.remove("nonexistent")

    def test_merge_assertions(self) -> None:
        ps = PolicySet()
        ps.add(PolicyDefinition(
            name="security",
            assertions={"policy_violation": ["pii_leak"], "max_chars": 600},
            applies_to=["support"],
        ))
        ps.add(PolicyDefinition(
            name="safety",
            assertions={"policy_violation": ["prompt_injection"], "max_chars": 800},
            applies_to=["support"],
        ))

        merged = ps.merge_assertions_for_scenario(["support"])
        assert "pii_leak" in merged["policy_violation"]
        assert "prompt_injection" in merged["policy_violation"]

    def test_roundtrip(self) -> None:
        ps = PolicySet("roundtrip")
        ps.add(PolicyDefinition(name="p1", assertions={"max_chars": 500}))
        ps.add(PolicyDefinition(name="p2", severity="warning"))

        d = ps.to_dict()
        restored = PolicySet.from_dict(d)
        assert restored.name == "roundtrip"
        assert len(restored.list_policies()) == 2


class TestPolicyManager:
    def test_save_and_load_central(self, tmp_dir: Path) -> None:
        mgr = PolicyManager(str(tmp_dir / "policies"))
        ps = PolicySet("central")
        ps.add(PolicyDefinition(name="no-pii", assertions={"policy_violation": ["pii_leak"]}))
        mgr.save_central(ps)

        loaded = mgr.load_central()
        assert loaded.get("no-pii") is not None

    def test_effective_policies(self, tmp_dir: Path) -> None:
        mgr = PolicyManager(str(tmp_dir / "policies"))

        central = PolicySet("central")
        central.add(PolicyDefinition(name="safety", severity="error", overridable=True))
        central.add(PolicyDefinition(name="locked", severity="error", overridable=False))
        mgr.save_central(central)
        mgr.load_central()

        overrides = PolicySet("overrides")
        overrides.add(PolicyDefinition(name="safety", severity="warning"))
        overrides.add(PolicyDefinition(name="locked", severity="warning"))
        mgr.save_overrides(overrides)
        mgr.load_overrides()

        effective = mgr.effective_policies()
        safety = effective.get("safety")
        assert safety is not None
        assert safety.severity == "warning"

        locked = effective.get("locked")
        assert locked is not None
        assert locked.severity == "error"

    def test_validate_overrides(self, tmp_dir: Path) -> None:
        mgr = PolicyManager(str(tmp_dir / "policies"))

        central = PolicySet("central")
        central.add(PolicyDefinition(name="locked", overridable=False))
        mgr.save_central(central)
        mgr._central = central

        overrides = PolicySet("overrides")
        overrides.add(PolicyDefinition(name="locked", severity="warning"))
        mgr._overrides = overrides

        errors = mgr.validate_overrides()
        assert len(errors) == 1
        assert "locked" in errors[0]

    def test_empty_manager(self, tmp_dir: Path) -> None:
        mgr = PolicyManager(str(tmp_dir / "empty-policies"))
        effective = mgr.effective_policies()
        assert len(effective.list_policies()) == 0
