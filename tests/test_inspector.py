"""Tests for pip_verv.inspector."""

import datetime
from unittest.mock import MagicMock, patch

from pip_verv.inspector import (
    find_blockers,
    find_installable_version,
    get_installed_packages,
    get_package_requirements,
)
from pip_verv.models import PackageRelease


class TestGetInstalledPackages:
    def test_should_return_installed_packages_as_dict(self) -> None:
        mock_dist = MagicMock()
        mock_dist.metadata = {"Name": "requests", "Version": "2.28.0"}
        mock_dist.version = "2.28.0"

        with patch("pip_verv.inspector.distributions", return_value=[mock_dist]):
            result = get_installed_packages()

        assert result == {"requests": "2.28.0"}

    def test_should_normalize_names_to_lowercase(self) -> None:
        mock_dist = MagicMock()
        mock_dist.metadata = {"Name": "Requests", "Version": "2.28.0"}
        mock_dist.version = "2.28.0"

        with patch("pip_verv.inspector.distributions", return_value=[mock_dist]):
            result = get_installed_packages()

        assert "requests" in result

    def test_should_return_empty_dict_when_distributions_raises(self) -> None:
        with patch("pip_verv.inspector.distributions", side_effect=Exception("fail")):
            result = get_installed_packages()

        assert result == {}

    def test_should_skip_packages_without_name(self) -> None:
        mock_dist = MagicMock()
        mock_dist.metadata = {"Name": None, "Version": "1.0.0"}
        mock_dist.version = "1.0.0"

        with patch("pip_verv.inspector.distributions", return_value=[mock_dist]):
            result = get_installed_packages()

        assert result == {}


class TestGetPackageRequirements:
    def test_should_return_requirements_list(self) -> None:
        with patch(
            "pip_verv.inspector.requires",
            return_value=["requests>=2.0", "click>=7.0"],
        ):
            result = get_package_requirements("mypackage")

        assert result == ["requests>=2.0", "click>=7.0"]

    def test_should_filter_extras_conditional_requirements(self) -> None:
        with patch(
            "pip_verv.inspector.requires",
            return_value=["requests>=2.0", "pytest>=7.0; extra=='dev'"],
        ):
            result = get_package_requirements("mypackage")

        assert result == ["requests>=2.0"]

    def test_should_return_empty_list_when_package_not_found(self) -> None:
        from importlib.metadata import PackageNotFoundError

        with patch(
            "pip_verv.inspector.requires",
            side_effect=PackageNotFoundError("not found"),
        ):
            result = get_package_requirements("nonexistent")

        assert result == []

    def test_should_return_empty_list_when_requires_returns_none(self) -> None:
        with patch("pip_verv.inspector.requires", return_value=None):
            result = get_package_requirements("mypackage")

        assert result == []


class TestFindBlockers:
    def test_should_find_blocker_when_constraint_excludes_latest(self) -> None:
        installed = {"pkg-a": "1.0.0"}
        with patch(
            "pip_verv.inspector.get_package_requirements",
            return_value=["requests>=2.0,<3.0"],
        ):
            result = find_blockers("requests", "3.1.0", installed)

        assert result == ["pkg-a (<3.0,>=2.0)"]

    def test_should_return_empty_when_no_blockers(self) -> None:
        installed = {"pkg-a": "1.0.0"}
        with patch(
            "pip_verv.inspector.get_package_requirements",
            return_value=["requests>=2.0"],
        ):
            result = find_blockers("requests", "3.1.0", installed)

        assert result == []

    def test_should_handle_multiple_blockers(self) -> None:
        installed = {"pkg-a": "1.0.0", "pkg-b": "2.0.0"}
        with patch(
            "pip_verv.inspector.get_package_requirements",
            return_value=["requests>=2.0,<3.0"],
        ):
            result = find_blockers("requests", "3.1.0", installed)

        assert result == ["pkg-a (<3.0,>=2.0)", "pkg-b (<3.0,>=2.0)"]

    def test_should_skip_malformed_requirements(self) -> None:
        installed = {"pkg-a": "1.0.0"}
        with patch(
            "pip_verv.inspector.get_package_requirements",
            return_value=["!!!invalid!!!"],
        ):
            result = find_blockers("requests", "3.1.0", installed)

        assert result == []

    def test_should_return_empty_for_invalid_latest_version(self) -> None:
        installed = {"pkg-a": "1.0.0"}
        result = find_blockers("requests", "not-a-version", installed)

        assert result == []

    def test_should_be_case_insensitive(self) -> None:
        installed = {"pkg-a": "1.0.0"}
        with patch(
            "pip_verv.inspector.get_package_requirements",
            return_value=["Requests>=2.0,<3.0"],
        ):
            result = find_blockers("REQUESTS", "3.1.0", installed)

        assert result == ["pkg-a (<3.0,>=2.0)"]

    def test_should_return_sorted_list(self) -> None:
        installed = {"pkg-z": "1.0.0", "pkg-a": "1.0.0"}
        with patch(
            "pip_verv.inspector.get_package_requirements",
            return_value=["requests>=2.0,<3.0"],
        ):
            result = find_blockers("requests", "3.1.0", installed)

        assert result == ["pkg-a (<3.0,>=2.0)", "pkg-z (<3.0,>=2.0)"]


def _make_release(version: str, date_str: str) -> PackageRelease:
    return PackageRelease(
        version=version,
        release_date=datetime.datetime.fromisoformat(date_str),
        yanked=False,
    )


class TestFindInstallableVersion:
    def test_should_return_highest_satisfying_version(self) -> None:
        installed = {"streamlit": "1.43.0"}
        releases = [
            _make_release("3.0.2", "2025-01-01T00:00:00"),
            _make_release("2.3.3", "2024-06-01T00:00:00"),
            _make_release("2.0.0", "2023-01-01T00:00:00"),
        ]
        with patch(
            "pip_verv.inspector.get_package_requirements",
            return_value=["pandas<3,>=1.4.0"],
        ):
            result = find_installable_version("pandas", releases, installed)

        assert result == "2.3.3"

    def test_should_return_none_when_no_constraints_found(self) -> None:
        installed = {"some-pkg": "1.0.0"}
        releases = [_make_release("3.0.2", "2025-01-01T00:00:00")]
        with patch(
            "pip_verv.inspector.get_package_requirements",
            return_value=["click>=7.0"],  # requires click, not pandas
        ):
            result = find_installable_version("pandas", releases, installed)

        assert result is None

    def test_should_return_none_when_no_release_satisfies_constraints(self) -> None:
        installed = {"pkg-a": "1.0.0"}
        releases = [
            _make_release("3.0.0", "2025-01-01T00:00:00"),
            _make_release("4.0.0", "2025-06-01T00:00:00"),
        ]
        with patch(
            "pip_verv.inspector.get_package_requirements",
            return_value=["requests<2.0"],
        ):
            result = find_installable_version("requests", releases, installed)

        assert result is None

    def test_should_combine_constraints_from_multiple_packages(self) -> None:
        installed = {"pkg-a": "1.0.0", "pkg-b": "2.0.0"}
        releases = [
            _make_release("3.0.0", "2025-01-01T00:00:00"),
            _make_release("2.5.0", "2024-06-01T00:00:00"),
            _make_release("2.0.0", "2024-01-01T00:00:00"),
        ]

        def _fake_reqs(pkg: str) -> list[str]:
            return {
                "pkg-a": ["requests<3.0"],
                "pkg-b": ["requests>=2.0,<2.5"],  # further restricts
            }.get(pkg, [])

        with patch(
            "pip_verv.inspector.get_package_requirements",
            side_effect=_fake_reqs,
        ):
            result = find_installable_version("requests", releases, installed)

        # Combined: <3.0 AND >=2.0,<2.5 → only 2.0.0 qualifies
        assert result == "2.0.0"
