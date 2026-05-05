from pathlib import Path

import pytest

from pip_verv.config import ConfigError, VervConfig, load_config, merge_config


class TestLoadConfig:
    def test_should_return_defaults_when_no_config_file(self, tmp_path: Path) -> None:
        result = load_config(tmp_path)

        assert result == VervConfig()

    def test_should_return_defaults_when_empty_config_file(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".verv.toml").write_text("")

        result = load_config(tmp_path)

        assert result == VervConfig()

    def test_should_parse_all_fields_correctly(self, tmp_path: Path) -> None:
        (tmp_path / ".verv.toml").write_text(
            'ignore = ["requests", "boto3"]\n'
            "gap_fail = 365\n"
            "score_fail = 70.0\n"
            "max_major = 2\n"
            "max_outdated = 5\n"
            "cache_ttl = 12\n"
        )

        result = load_config(tmp_path)

        assert result.ignore == ["requests", "boto3"]
        assert result.gap_fail == 365
        assert result.score_fail == 70.0
        assert result.max_major == 2
        assert result.max_outdated == 5
        assert result.cache_ttl == 12

    def test_should_ignore_unknown_keys_in_toml(self, tmp_path: Path) -> None:
        (tmp_path / ".verv.toml").write_text('unknown_key = "value"\ngap_fail = 100\n')

        result = load_config(tmp_path)

        assert result.gap_fail == 100

    def test_should_raise_config_error_on_malformed_toml(self, tmp_path: Path) -> None:
        (tmp_path / ".verv.toml").write_text("this is [not valid toml !!!")

        with pytest.raises(ConfigError, match="Malformed .verv.toml"):
            load_config(tmp_path)

    def test_should_use_default_cache_ttl_when_not_set(self, tmp_path: Path) -> None:
        (tmp_path / ".verv.toml").write_text("gap_fail = 30\n")

        result = load_config(tmp_path)

        assert result.cache_ttl == 24


class TestMergeConfig:
    def test_should_not_override_file_value_when_cli_is_none(self) -> None:
        file_config = VervConfig(gap_fail=365)

        result = merge_config(file_config, gap_fail=None)

        assert result.gap_fail == 365

    def test_should_override_file_value_when_cli_is_non_none(self) -> None:
        file_config = VervConfig(gap_fail=365)

        result = merge_config(file_config, gap_fail=180)

        assert result.gap_fail == 180

    def test_should_override_score_fail_from_cli(self) -> None:
        file_config = VervConfig(score_fail=60.0)

        result = merge_config(file_config, score_fail=80.0)

        assert result.score_fail == 80.0

    def test_should_not_override_score_fail_when_cli_none(self) -> None:
        file_config = VervConfig(score_fail=60.0)

        result = merge_config(file_config, score_fail=None)

        assert result.score_fail == 60.0

    def test_should_override_ignore_list_from_cli(self) -> None:
        file_config = VervConfig(ignore=["boto3"])

        result = merge_config(file_config, ignore=["requests"])

        assert result.ignore == ["requests"]

    def test_should_keep_original_when_all_cli_overrides_none(self) -> None:
        file_config = VervConfig(
            ignore=["boto3"], gap_fail=100, score_fail=70.0, max_major=1
        )

        result = merge_config(
            file_config,
            ignore=None,
            gap_fail=None,
            score_fail=None,
            max_major=None,
        )

        assert result == file_config
