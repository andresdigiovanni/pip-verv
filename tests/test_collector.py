import datetime
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import respx

import pip_verv.collector as collector_module
from pip_verv.collector import (
    collect,
    get_latest_stable,
)
from pip_verv.models import PackageRelease

PYPI_BASE = "https://pypi.org/pypi"

REQUESTS_PYPI_RESPONSE = {
    "releases": {
        "2.31.0": [
            {
                "upload_time": "2023-05-22T15:00:00",
                "yanked": False,
            }
        ],
        "2.28.0": [
            {
                "upload_time": "2022-06-09T10:00:00",
                "yanked": False,
            }
        ],
        "3.0.0a1": [
            {
                "upload_time": "2024-01-01T00:00:00",
                "yanked": False,
            }
        ],
    }
}


def _make_pypi_response(version: str, upload_time: str, yanked: bool = False) -> dict:  # type: ignore[type-arg]
    return {
        "releases": {
            version: [{"upload_time": upload_time, "yanked": yanked}],
        }
    }


class TestCollect:
    @respx.mock
    async def test_should_fetch_and_return_correct_releases(self) -> None:
        respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json=REQUESTS_PYPI_RESPONSE)
        )

        with patch.object(
            collector_module, "CACHE_DIR", Path("/tmp/nonexistent_cache_abc123")
        ):
            result = await collect(["requests"], cache_ttl=24, no_cache=True)

        assert "requests" in result
        versions = [r.version for r in result["requests"]]
        assert "2.31.0" in versions
        assert "2.28.0" in versions

    @respx.mock
    async def test_should_exclude_prerelease_versions(self) -> None:
        respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json=REQUESTS_PYPI_RESPONSE)
        )

        with patch.object(
            collector_module, "CACHE_DIR", Path("/tmp/nonexistent_cache_abc123")
        ):
            result = await collect(["requests"], cache_ttl=24, no_cache=True)

        versions = [r.version for r in result["requests"]]
        assert "3.0.0a1" not in versions

    @respx.mock
    async def test_should_exclude_yanked_versions(self) -> None:
        data = {
            "releases": {
                "2.31.0": [{"upload_time": "2023-05-22T15:00:00", "yanked": True}],
                "2.28.0": [{"upload_time": "2022-06-09T10:00:00", "yanked": False}],
            }
        }
        respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json=data)
        )

        with patch.object(
            collector_module, "CACHE_DIR", Path("/tmp/nonexistent_cache_abc123")
        ):
            result = await collect(["requests"], cache_ttl=24, no_cache=True)

        versions = [r.version for r in result["requests"]]
        assert "2.31.0" not in versions
        assert "2.28.0" in versions

    @respx.mock
    async def test_should_return_empty_list_for_404(self) -> None:
        respx.get(f"{PYPI_BASE}/nonexistent-pkg/json").mock(
            return_value=httpx.Response(404)
        )

        with patch.object(
            collector_module, "CACHE_DIR", Path("/tmp/nonexistent_cache_abc123")
        ):
            result = await collect(["nonexistent-pkg"], cache_ttl=24, no_cache=True)

        assert result["nonexistent-pkg"] == []

    @respx.mock
    async def test_should_return_empty_list_on_network_timeout(self) -> None:
        respx.get(f"{PYPI_BASE}/requests/json").mock(
            side_effect=httpx.TimeoutException("timeout")
        )

        with patch.object(
            collector_module, "CACHE_DIR", Path("/tmp/nonexistent_cache_abc123")
        ):
            result = await collect(["requests"], cache_ttl=24, no_cache=True)

        assert result["requests"] == []

    @respx.mock
    async def test_should_exclude_versions_with_missing_upload_time(self) -> None:
        data = {
            "releases": {
                "2.31.0": [{"upload_time": None, "yanked": False}],
                "2.28.0": [{"upload_time": "2022-06-09T10:00:00", "yanked": False}],
            }
        }
        respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json=data)
        )

        with patch.object(
            collector_module, "CACHE_DIR", Path("/tmp/nonexistent_cache_abc123")
        ):
            result = await collect(["requests"], cache_ttl=24, no_cache=True)

        versions = [r.version for r in result["requests"]]
        assert "2.31.0" not in versions
        assert "2.28.0" in versions

    @respx.mock
    async def test_should_return_empty_list_for_empty_releases_dict(self) -> None:
        respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json={"releases": {}})
        )

        with patch.object(
            collector_module, "CACHE_DIR", Path("/tmp/nonexistent_cache_abc123")
        ):
            result = await collect(["requests"], cache_ttl=24, no_cache=True)

        assert result["requests"] == []


class TestCaching:
    @respx.mock
    async def test_should_not_make_http_call_on_cache_hit(self, tmp_path: Path) -> None:
        route = respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json=REQUESTS_PYPI_RESPONSE)
        )

        with patch.object(collector_module, "CACHE_DIR", tmp_path):
            # First call writes cache
            await collect(["requests"], cache_ttl=24, no_cache=False)
            call_count_after_first = route.call_count
            # Second call should hit cache
            await collect(["requests"], cache_ttl=24, no_cache=False)
            call_count_after_second = route.call_count

        assert call_count_after_first == 1
        assert call_count_after_second == 1  # No additional call

    @respx.mock
    async def test_should_make_http_call_when_cache_expired(
        self, tmp_path: Path
    ) -> None:
        route = respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json=REQUESTS_PYPI_RESPONSE)
        )

        # Write a stale cache entry manually
        cache_file = tmp_path / "requests.json"
        stale_data = {
            "cached_at": "2020-01-01T00:00:00",  # way in the past
            "releases": [],
        }
        cache_file.write_text(json.dumps(stale_data))

        with patch.object(collector_module, "CACHE_DIR", tmp_path):
            await collect(["requests"], cache_ttl=24, no_cache=False)

        assert route.call_count == 1

    @respx.mock
    async def test_should_always_make_http_call_when_no_cache_true(
        self, tmp_path: Path
    ) -> None:
        route = respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json=REQUESTS_PYPI_RESPONSE)
        )

        with patch.object(collector_module, "CACHE_DIR", tmp_path):
            await collect(["requests"], cache_ttl=24, no_cache=True)
            await collect(["requests"], cache_ttl=24, no_cache=True)

        assert route.call_count == 2


class TestParseReleasesOrdering:
    @respx.mock
    async def test_should_order_by_version_not_by_upload_date(
        self, tmp_path: Path
    ) -> None:
        # Backport patch (2.31.5) uploaded AFTER the major release (3.0.0).
        # The major release must still be considered the latest.
        data = {
            "releases": {
                "3.0.0": [{"upload_time": "2024-01-01T00:00:00", "yanked": False}],
                "2.31.5": [
                    {"upload_time": "2024-06-01T00:00:00", "yanked": False}
                ],  # newer date, lower version
            }
        }
        respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json=data)
        )

        with patch.object(collector_module, "CACHE_DIR", tmp_path):
            result = await collect(["requests"], cache_ttl=24, no_cache=True)

        releases = result["requests"]
        assert releases[0].version == "3.0.0"

    @respx.mock
    async def test_should_return_highest_version_as_latest_stable(
        self, tmp_path: Path
    ) -> None:
        data = {
            "releases": {
                "3.0.0": [{"upload_time": "2024-01-01T00:00:00", "yanked": False}],
                "2.31.5": [{"upload_time": "2024-06-01T00:00:00", "yanked": False}],
            }
        }
        respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json=data)
        )

        with patch.object(collector_module, "CACHE_DIR", tmp_path):
            result = await collect(["requests"], cache_ttl=24, no_cache=True)

        latest = get_latest_stable(result["requests"])
        assert latest is not None
        assert latest.version == "3.0.0"


class TestGetLatestStable:
    def test_should_return_first_non_yanked_release(self) -> None:
        releases = [
            PackageRelease(
                version="2.31.0",
                release_date=datetime.datetime(2023, 5, 22),
                yanked=False,
            ),
            PackageRelease(
                version="2.28.0",
                release_date=datetime.datetime(2022, 6, 9),
                yanked=False,
            ),
        ]

        result = get_latest_stable(releases)

        assert result is not None
        assert result.version == "2.31.0"

    def test_should_skip_yanked_releases(self) -> None:
        releases = [
            PackageRelease(
                version="2.31.0",
                release_date=datetime.datetime(2023, 5, 22),
                yanked=True,
            ),
            PackageRelease(
                version="2.28.0",
                release_date=datetime.datetime(2022, 6, 9),
                yanked=False,
            ),
        ]

        result = get_latest_stable(releases)

        assert result is not None
        assert result.version == "2.28.0"

    def test_should_return_none_for_empty_list(self) -> None:
        result = get_latest_stable([])

        assert result is None

    def test_should_return_none_when_all_releases_yanked(self) -> None:
        releases = [
            PackageRelease(
                version="2.31.0",
                release_date=datetime.datetime(2023, 5, 22),
                yanked=True,
            ),
        ]

        result = get_latest_stable(releases)

        assert result is None


class TestConcurrency:
    @respx.mock
    async def test_should_handle_concurrent_requests_for_multiple_packages(
        self, tmp_path: Path
    ) -> None:
        packages = ["requests", "flask", "django", "urllib3", "celery"]
        for pkg in packages:
            respx.get(f"{PYPI_BASE}/{pkg}/json").mock(
                return_value=httpx.Response(200, json=REQUESTS_PYPI_RESPONSE)
            )

        with patch.object(collector_module, "CACHE_DIR", tmp_path):
            result = await collect(packages, cache_ttl=24, no_cache=True)

        assert len(result) == len(packages)
        for pkg in packages:
            assert isinstance(result[pkg], list)

    @respx.mock
    async def test_should_not_corrupt_cache_on_repeated_writes(
        self, tmp_path: Path
    ) -> None:
        respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json=REQUESTS_PYPI_RESPONSE)
        )

        with patch.object(collector_module, "CACHE_DIR", tmp_path):
            await collect(["requests"], cache_ttl=24, no_cache=True)
            await collect(["requests"], cache_ttl=24, no_cache=True)

        cache_file = tmp_path / "requests.json"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert "releases" in data
        assert "cached_at" in data


class TestLargeInputs:
    @respx.mock
    async def test_should_handle_large_number_of_packages(
        self, tmp_path: Path
    ) -> None:
        packages = [f"pkg{i}" for i in range(50)]
        for pkg in packages:
            respx.get(f"{PYPI_BASE}/{pkg}/json").mock(
                return_value=httpx.Response(200, json=REQUESTS_PYPI_RESPONSE)
            )

        with patch.object(collector_module, "CACHE_DIR", tmp_path):
            result = await collect(packages, cache_ttl=24, no_cache=True)

        assert len(result) == 50

    @respx.mock
    async def test_should_handle_package_with_many_releases(
        self, tmp_path: Path
    ) -> None:
        many_releases = {
            str(i): [{"upload_time": f"2020-01-{i:02d}T00:00:00", "yanked": False}]
            for i in range(1, 29)
        }
        respx.get(f"{PYPI_BASE}/requests/json").mock(
            return_value=httpx.Response(200, json={"releases": many_releases})
        )

        with patch.object(collector_module, "CACHE_DIR", tmp_path):
            result = await collect(["requests"], cache_ttl=24, no_cache=True)

        assert len(result["requests"]) == 28
