"""Tests for authentication and RBAC."""

from __future__ import annotations

from pathlib import Path

from contractops.auth import ROLE_PERMISSIONS, AuthManager, Permission, User


class TestUser:
    def test_permissions_by_role(self) -> None:
        viewer = User("v1", role="viewer")
        assert viewer.has_permission(Permission.READ)
        assert not viewer.has_permission(Permission.WRITE)

        admin = User("a1", role="admin")
        for perm in Permission.ALL:
            assert admin.has_permission(perm)

    def test_developer_permissions(self) -> None:
        dev = User("d1", role="developer")
        assert dev.has_permission(Permission.READ)
        assert dev.has_permission(Permission.WRITE)
        assert not dev.has_permission(Permission.APPROVE)

    def test_approver_permissions(self) -> None:
        approver = User("ap1", role="approver")
        assert approver.has_permission(Permission.APPROVE)
        assert not approver.has_permission(Permission.ADMIN)

    def test_to_dict(self) -> None:
        user = User("u1", email="u@test.com", role="admin", tenant_id="t1")
        d = user.to_dict()
        assert d["user_id"] == "u1"
        assert d["tenant_id"] == "t1"


class TestAuthManager:
    def test_create_and_get_user(self, tmp_dir: Path) -> None:
        mgr = AuthManager(str(tmp_dir / "auth"))
        user = mgr.create_user("user1", email="u@test.com", role="developer")
        assert user.user_id == "user1"
        assert user.role == "developer"

        loaded = mgr.get_user("user1")
        assert loaded is not None
        assert loaded.email == "u@test.com"

    def test_invalid_role_raises(self, tmp_dir: Path) -> None:
        mgr = AuthManager(str(tmp_dir / "auth"))
        try:
            mgr.create_user("bad", role="superuser")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid role" in str(e)

    def test_update_role(self, tmp_dir: Path) -> None:
        mgr = AuthManager(str(tmp_dir / "auth"))
        mgr.create_user("user1", role="viewer")
        updated = mgr.update_role("user1", "admin")
        assert updated is not None
        assert updated.role == "admin"

    def test_delete_user(self, tmp_dir: Path) -> None:
        mgr = AuthManager(str(tmp_dir / "auth"))
        mgr.create_user("to-delete")
        assert mgr.delete_user("to-delete")
        assert mgr.get_user("to-delete") is None

    def test_list_users(self, tmp_dir: Path) -> None:
        mgr = AuthManager(str(tmp_dir / "auth"))
        mgr.create_user("u1", tenant_id="t1")
        mgr.create_user("u2", tenant_id="t1")
        mgr.create_user("u3", tenant_id="t2")

        all_users = mgr.list_users()
        assert len(all_users) == 3

        t1_users = mgr.list_users(tenant_id="t1")
        assert len(t1_users) == 2

    def test_api_key_lifecycle(self, tmp_dir: Path) -> None:
        mgr = AuthManager(str(tmp_dir / "auth"))
        mgr.create_user("key-user", role="developer")

        key = mgr.generate_api_key("key-user", description="CI key")
        assert len(key) > 0

        user = mgr.authenticate_key(key)
        assert user is not None
        assert user.user_id == "key-user"

        assert mgr.revoke_key(key)
        assert mgr.authenticate_key(key) is None

    def test_authenticate_invalid_key(self, tmp_dir: Path) -> None:
        mgr = AuthManager(str(tmp_dir / "auth"))
        assert mgr.authenticate_key("invalid-key-12345") is None

    def test_tenant_isolation(self, tmp_dir: Path) -> None:
        mgr = AuthManager(str(tmp_dir / "auth"))
        user_t1 = mgr.create_user("u1", tenant_id="tenant-a", role="admin")
        mgr.create_user("u2", tenant_id="tenant-b", role="admin")

        assert mgr.check_authorization(user_t1, Permission.ADMIN, tenant_id="tenant-a")
        assert not mgr.check_authorization(user_t1, Permission.ADMIN, tenant_id="tenant-b")

    def test_persistence(self, tmp_dir: Path) -> None:
        path = str(tmp_dir / "persist-auth")
        mgr1 = AuthManager(path)
        mgr1.create_user("persist-user", role="admin")
        key = mgr1.generate_api_key("persist-user")

        mgr2 = AuthManager(path)
        loaded = mgr2.get_user("persist-user")
        assert loaded is not None
        assert mgr2.authenticate_key(key) is not None


class TestRolePermissions:
    def test_all_roles_defined(self) -> None:
        expected = {"viewer", "developer", "approver", "admin"}
        assert set(ROLE_PERMISSIONS.keys()) == expected

    def test_admin_has_all(self) -> None:
        assert ROLE_PERMISSIONS["admin"] == Permission.ALL
