import json
from pathlib import Path

from contractops.config import Config, ThresholdProfile, find_config, load_config


class TestLoadConfig:
    def test_default_config(self):
        config = load_config(path=None)
        assert isinstance(config, Config)
        assert config.default_executor == "mock-v1"
        assert config.storage.backend == "local"

    def test_from_yaml(self, tmp_dir: Path):
        cfg = tmp_dir / "contractops.yaml"
        cfg.write_text(
            """\
scenarios_dir: my_scenarios
default_executor: openai
thresholds:
  production:
    min_similarity: 0.95
    min_score: 90
    require_baseline: true
storage:
  backend: s3
  bucket: my-bucket
  prefix: baselines
""",
            encoding="utf-8",
        )
        config = load_config(cfg)
        assert config.scenarios_dir == "my_scenarios"
        assert config.default_executor == "openai"
        assert config.storage.backend == "s3"
        assert config.storage.bucket == "my-bucket"
        prod = config.threshold_for("production")
        assert prod.min_similarity == 0.95
        assert prod.min_score == 90
        assert prod.require_baseline is True

    def test_from_json(self, tmp_dir: Path):
        cfg = tmp_dir / "contractops.json"
        cfg.write_text(
            json.dumps({"default_executor": "mock-v2", "output_format": "json"}),
            encoding="utf-8",
        )
        config = load_config(cfg)
        assert config.default_executor == "mock-v2"
        assert config.output_format == "json"


class TestThresholdFor:
    def test_returns_named_profile(self):
        config = Config(thresholds={
            "staging": ThresholdProfile(min_similarity=0.8, min_score=75),
        })
        t = config.threshold_for("staging")
        assert t.min_similarity == 0.8
        assert t.min_score == 75

    def test_falls_back_to_default_profile(self):
        config = Config(thresholds={
            "default": ThresholdProfile(min_similarity=0.85, min_score=80),
        })
        t = config.threshold_for("production")
        assert t.min_similarity == 0.85

    def test_falls_back_to_class_defaults(self):
        config = Config()
        t = config.threshold_for("anything")
        assert t.min_similarity == 0.85
        assert t.min_score == 80


class TestFindConfig:
    def test_finds_yaml(self, tmp_dir: Path):
        (tmp_dir / "contractops.yaml").write_text("x: 1", encoding="utf-8")
        found = find_config(tmp_dir)
        assert found is not None
        assert found.name == "contractops.yaml"

    def test_finds_json(self, tmp_dir: Path):
        (tmp_dir / "contractops.json").write_text("{}", encoding="utf-8")
        found = find_config(tmp_dir)
        assert found is not None
        assert found.name == "contractops.json"

    def test_returns_none_when_missing(self, tmp_dir: Path):
        found = find_config(tmp_dir)
        assert found is None
