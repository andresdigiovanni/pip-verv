import asyncio
import datetime
import json
from pathlib import Path

import httpx
from packaging.version import Version

from pip_verv.models import PackageRelease

PYPI_BASE = "https://pypi.org/pypi"
CACHE_DIR = Path.home() / ".pip-verv" / "cache"


class CollectorError(Exception):
    pass


async def collect(
    names: list[str],
    *,
    cache_ttl: int,
    no_cache: bool,
) -> dict[str, list[PackageRelease]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [
            _fetch_package(client, name, cache_ttl=cache_ttl, no_cache=no_cache)
            for name in names
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    output: dict[str, list[PackageRelease]] = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            output[name.lower()] = []
        else:
            output[name.lower()] = result  # type: ignore[assignment]
    return output


async def _fetch_package(
    client: httpx.AsyncClient,
    name: str,
    *,
    cache_ttl: int,
    no_cache: bool,
) -> list[PackageRelease]:
    cached = _read_cache(name, cache_ttl) if not no_cache else None
    if cached is not None:
        return cached
    try:
        response = await client.get(f"{PYPI_BASE}/{name}/json")
    except httpx.TimeoutException as e:
        raise CollectorError(f"Timeout fetching {name}") from e
    except httpx.RequestError as e:
        raise CollectorError(f"Request error for {name}") from e
    if response.status_code == 404:
        return []
    response.raise_for_status()
    data = response.json()
    releases = _parse_releases(data)
    _write_cache(name, releases)
    return releases


def _parse_releases(data: dict[str, object]) -> list[PackageRelease]:
    releases: list[PackageRelease] = []
    releases_data = data.get("releases", {})
    if not isinstance(releases_data, dict):
        return releases
    for version_str, files in releases_data.items():
        try:
            v = Version(version_str)
        except Exception:
            continue
        if v.is_prerelease:
            continue
        if not isinstance(files, list) or not files:
            continue
        if any(isinstance(f, dict) and f.get("yanked", False) for f in files):
            continue
        first_file = files[0]
        if not isinstance(first_file, dict):
            continue
        upload_time_str = first_file.get("upload_time")
        if not upload_time_str:
            continue
        try:
            release_date = datetime.datetime.fromisoformat(str(upload_time_str))
        except ValueError:
            continue
        releases.append(
            PackageRelease(version=str(v), release_date=release_date, yanked=False)
        )
    releases.sort(key=lambda r: r.release_date, reverse=True)
    return releases


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name.lower()}.json"


def _read_cache(name: str, cache_ttl: int) -> list[PackageRelease] | None:
    path = _cache_path(name)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        cached_at = datetime.datetime.fromisoformat(data["cached_at"])
        age_hours = (
            datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
            - cached_at
        ).total_seconds() / 3600
        if age_hours > cache_ttl:
            return None
        return [
            PackageRelease(
                version=r["version"],
                release_date=datetime.datetime.fromisoformat(r["release_date"]),
                yanked=r["yanked"],
            )
            for r in data["releases"]
        ]
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _write_cache(name: str, releases: list[PackageRelease]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(name)
    data = {
        "cached_at": datetime.datetime.now(datetime.UTC)
        .replace(tzinfo=None)
        .isoformat(),
        "releases": [
            {
                "version": r.version,
                "release_date": r.release_date.isoformat(),
                "yanked": r.yanked,
            }
            for r in releases
        ],
    }
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w") as f:
            json.dump(data, f)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def get_latest_stable(releases: list[PackageRelease]) -> PackageRelease | None:
    for r in releases:
        if not r.yanked:
            return r
    return None
