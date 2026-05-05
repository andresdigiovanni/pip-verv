import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass
class VervConfig:
    ignore: list[str] = field(default_factory=list)
    gap_fail: int | None = None
    score_fail: float | None = None
    max_major: int | None = None
    max_outdated: int | None = None
    cache_ttl: int = 24


def load_config(path: Path) -> VervConfig:
    config_file = path / ".verv.toml"
    if not config_file.exists():
        return VervConfig()
    try:
        with open(config_file, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Malformed .verv.toml: {e}") from e
    return VervConfig(
        ignore=data.get("ignore", []),
        gap_fail=data.get("gap_fail"),
        score_fail=data.get("score_fail"),
        max_major=data.get("max_major"),
        max_outdated=data.get("max_outdated"),
        cache_ttl=data.get("cache_ttl", 24),
    )


def merge_config(file_config: VervConfig, **cli_overrides: object) -> VervConfig:
    overrides: dict[str, Any] = {
        k: v for k, v in cli_overrides.items() if v is not None
    }
    return replace(file_config, **overrides)
