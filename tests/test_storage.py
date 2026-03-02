from pathlib import Path

import pytest

from contractops.storage import LocalStorage, build_storage


class TestLocalStorage:
    def test_save_and_load(self, tmp_dir: Path):
        storage = LocalStorage(str(tmp_dir / "baselines"))
        payload = {"data": "hello", "num": 42}
        location = storage.save("test-key", payload)
        assert "test-key" in location

        loaded = storage.load("test-key")
        assert loaded == payload

    def test_exists(self, tmp_dir: Path):
        storage = LocalStorage(str(tmp_dir / "baselines"))
        assert not storage.exists("missing")
        storage.save("present", {"a": 1})
        assert storage.exists("present")

    def test_list_keys(self, tmp_dir: Path):
        storage = LocalStorage(str(tmp_dir / "baselines"))
        storage.save("alpha", {"a": 1})
        storage.save("beta", {"b": 2})
        storage.save("gamma", {"c": 3})
        keys = storage.list_keys()
        assert sorted(keys) == ["alpha", "beta", "gamma"]

    def test_list_keys_empty_dir(self, tmp_dir: Path):
        storage = LocalStorage(str(tmp_dir / "empty"))
        assert storage.list_keys() == []

    def test_delete(self, tmp_dir: Path):
        storage = LocalStorage(str(tmp_dir / "baselines"))
        storage.save("to-delete", {"x": 1})
        assert storage.exists("to-delete")
        storage.delete("to-delete")
        assert not storage.exists("to-delete")

    def test_delete_nonexistent(self, tmp_dir: Path):
        storage = LocalStorage(str(tmp_dir / "baselines"))
        storage.delete("nope")

    def test_load_nonexistent_raises(self, tmp_dir: Path):
        storage = LocalStorage(str(tmp_dir / "baselines"))
        with pytest.raises(FileNotFoundError):
            storage.load("nope")

    def test_key_sanitization(self, tmp_dir: Path):
        storage = LocalStorage(str(tmp_dir / "baselines"))
        storage.save("path/with/slashes", {"v": 1})
        loaded = storage.load("path/with/slashes")
        assert loaded == {"v": 1}


class TestBuildStorage:
    def test_local_default(self):
        storage = build_storage()
        assert isinstance(storage, LocalStorage)

    def test_local_explicit(self, tmp_dir):
        storage = build_storage(backend="local", base_path=str(tmp_dir))
        assert isinstance(storage, LocalStorage)

    def test_s3_requires_bucket(self):
        with pytest.raises(ValueError, match="bucket"):
            build_storage(backend="s3")

    def test_gcs_requires_bucket(self):
        with pytest.raises(ValueError, match="bucket"):
            build_storage(backend="gcs")

    def test_unknown_backend(self):
        with pytest.raises(ValueError, match="Unknown"):
            build_storage(backend="ftp")
