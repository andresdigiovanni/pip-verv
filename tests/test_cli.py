import datetime
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from pip_verv.cli import app
from pip_verv.models import (
    Dependency,
    PackageRelease,
)

runner = CliRunner()


def _make_dep(name: str = "requests", spec: str = ">=2.28.0") -> Dependency:
    return Dependency(name=name, version_spec=spec, source="req.txt")


def _make_release(version: str, date_str: str) -> PackageRelease:
    return PackageRelease(
        version=version,
        release_date=datetime.datetime.fromisoformat(date_str),
        yanked=False,
    )


def _make_releases_map(
    name: str = "requests",
) -> dict[str, list[PackageRelease]]:
    return {
        name: [
            _make_release("2.31.0", "2023-05-22T15:00:00"),
            _make_release("2.28.0", "2022-06-09T10:00:00"),
        ]
    }


class TestAuditCommandNoFiles:
    def test_should_print_warning_when_no_dependency_files_found(
        self, tmp_path: Path
    ) -> None:
        result = runner.invoke(app, ["--path", str(tmp_path)])

        assert result.exit_code == 0
        assert "No dependency files found" in result.output


class TestAuditCommandJsonOutput:
    def test_should_produce_valid_json_with_format_json(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests>=2.28.0\n")

        with (
            patch(
                "pip_verv.cli.collect",
                new_callable=AsyncMock,
                return_value=_make_releases_map(),
            ),
            patch(
                "pip_verv.cli.get_installed_packages",
                return_value={"requests": "2.28.0"},
            ),
            patch("pip_verv.cli.find_blockers", return_value=[]),
        ):
            result = runner.invoke(
                app,
                ["--path", str(tmp_path), "--format", "json", "--no-cache"],
            )

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "score" in parsed
        assert "dependencies" in parsed


class TestAuditCommandPolicyEnforcement:
    def test_should_exit_1_when_score_below_score_fail(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests==2.28.0\n")

        # Simulate a large gap to drive score down
        releases_map = {
            "requests": [
                _make_release("3.0.0", "2026-01-01T00:00:00"),
                _make_release("2.28.0", "2020-01-01T00:00:00"),
            ]
        }

        with (
            patch(
                "pip_verv.cli.collect",
                new_callable=AsyncMock,
                return_value=releases_map,
            ),
            patch(
                "pip_verv.cli.get_installed_packages",
                return_value={"requests": "2.28.0"},
            ),
            patch("pip_verv.cli.find_blockers", return_value=[]),
        ):
            result = runner.invoke(
                app,
                [
                    "--path",
                    str(tmp_path),
                    "--format",
                    "json",
                    "--no-cache",
                    "--score-fail",
                    "99",
                ],
            )

        assert result.exit_code == 1

    def test_should_exit_0_when_score_above_score_fail(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests>=2.28.0\n")

        with (
            patch(
                "pip_verv.cli.collect",
                new_callable=AsyncMock,
                return_value=_make_releases_map(),
            ),
            patch(
                "pip_verv.cli.get_installed_packages",
                return_value={"requests": "2.28.0"},
            ),
            patch("pip_verv.cli.find_blockers", return_value=[]),
        ):
            result = runner.invoke(
                app,
                [
                    "--path",
                    str(tmp_path),
                    "--format",
                    "json",
                    "--no-cache",
                    "--score-fail",
                    "10",
                ],
            )

        assert result.exit_code == 0

    def test_should_exit_1_when_gap_exceeds_gap_fail(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests==2.28.0\n")

        releases_map = {
            "requests": [
                _make_release("2.31.0", "2023-05-22T15:00:00"),
                _make_release("2.28.0", "2022-06-09T10:00:00"),
            ]
        }

        with (
            patch(
                "pip_verv.cli.collect",
                new_callable=AsyncMock,
                return_value=releases_map,
            ),
            patch(
                "pip_verv.cli.get_installed_packages",
                return_value={"requests": "2.28.0"},
            ),
            patch("pip_verv.cli.find_blockers", return_value=[]),
        ):
            result = runner.invoke(
                app,
                [
                    "--path",
                    str(tmp_path),
                    "--format",
                    "json",
                    "--no-cache",
                    "--gap-fail",
                    "1",
                ],
            )

        assert result.exit_code == 1

    def test_should_exit_1_when_major_count_exceeds_max_major(
        self, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements.txt"
        # All three have MAJOR semver jumps AND large time gaps → MAJOR severity
        req_file.write_text("requests==1.0.0\nflask==1.0.0\ndjango==2.0.0\n")

        releases_map = {
            "requests": [
                _make_release("3.0.0", "2024-01-01T00:00:00"),  # major semver jump
                _make_release("1.0.0", "2018-01-01T00:00:00"),
            ],
            "flask": [
                _make_release("3.0.0", "2024-01-01T00:00:00"),  # major semver jump
                _make_release("1.0.0", "2018-01-01T00:00:00"),
            ],
            "django": [
                _make_release("4.0.0", "2024-01-01T00:00:00"),  # major semver jump
                _make_release("2.0.0", "2018-01-01T00:00:00"),
            ],
        }

        with (
            patch(
                "pip_verv.cli.collect",
                new_callable=AsyncMock,
                return_value=releases_map,
            ),
            patch(
                "pip_verv.cli.get_installed_packages",
                return_value={"requests": "1.0.0", "flask": "1.0.0", "django": "2.0.0"},
            ),
            patch("pip_verv.cli.find_blockers", return_value=[]),
        ):
            result = runner.invoke(
                app,
                [
                    "--path",
                    str(tmp_path),
                    "--format",
                    "json",
                    "--no-cache",
                    "--max-major",
                    "2",
                ],
            )

        assert result.exit_code == 1

    def test_should_exit_1_when_outdated_count_exceeds_max_outdated(
        self, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text(
            "requests==2.28.0\nflask==1.0.0\ndjango==2.0.0\nurllib3==1.0.0\ncelery==4.0.0\npillow==8.0.0\n"
        )

        # All are outdated (pinned old, newer available)
        releases_map = {
            pkg: [
                _make_release("99.0.0", "2024-01-01T00:00:00"),
                _make_release("1.0.0", "2022-01-01T00:00:00"),
            ]
            for pkg in ["requests", "flask", "django", "urllib3", "celery", "pillow"]
        }
        # fix requests and flask to have actual pinned versions
        for pkg, pinned in [
            ("requests", "2.28.0"),
            ("flask", "1.0.0"),
            ("django", "2.0.0"),
            ("urllib3", "1.0.0"),
            ("celery", "4.0.0"),
            ("pillow", "8.0.0"),
        ]:
            releases_map[pkg] = [
                _make_release("99.0.0", "2024-01-01T00:00:00"),
                _make_release(pinned, "2022-01-01T00:00:00"),
            ]

        with patch(
            "pip_verv.cli.collect",
            new_callable=AsyncMock,
            return_value=releases_map,
        ):
            result = runner.invoke(
                app,
                [
                    "--path",
                    str(tmp_path),
                    "--format",
                    "json",
                    "--no-cache",
                    "--max-outdated",
                    "5",
                ],
            )

        assert result.exit_code == 1


class TestAuditCommandIgnore:
    def test_should_exclude_ignored_packages(self, tmp_path: Path) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests>=2.28.0\nflask>=3.0\n")

        flask_releases = [_make_release("3.0.0", "2023-09-01T00:00:00")]
        releases_map = {
            **_make_releases_map(),
            "flask": flask_releases,
        }

        with patch(
            "pip_verv.cli.collect",
            new_callable=AsyncMock,
            return_value=releases_map,
        ) as _mock_collect:
            result = runner.invoke(
                app,
                [
                    "--path",
                    str(tmp_path),
                    "--format",
                    "json",
                    "--no-cache",
                    "--ignore",
                    "requests",
                ],
            )

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        dep_names = [d["name"].lower() for d in parsed["dependencies"]]
        assert "requests" not in dep_names


class TestAuditCommandSince:
    def test_should_filter_deps_with_latest_release_before_since_date(
        self, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests>=2.28.0\nflask>=3.0\n")

        releases_map = {
            "requests": [_make_release("2.31.0", "2023-05-22T15:00:00")],
            "flask": [_make_release("2.0.0", "2020-01-01T00:00:00")],
        }

        with patch(
            "pip_verv.cli.collect",
            new_callable=AsyncMock,
            return_value=releases_map,
        ):
            result = runner.invoke(
                app,
                [
                    "--path",
                    str(tmp_path),
                    "--format",
                    "json",
                    "--no-cache",
                    "--since",
                    "2023-01-01",
                ],
            )

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        dep_names = [d["name"].lower() for d in parsed["dependencies"]]
        assert "requests" in dep_names
        assert "flask" not in dep_names

    def test_should_exit_2_for_invalid_since_date_format(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["--path", str(tmp_path), "--since", "not-a-date"],
        )

        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# Integration: gap calculation for range constraints
# ---------------------------------------------------------------------------


class TestAuditCommandGapForRangeConstraints:
    """Verify that range constraints produce non-zero gaps when the constraint
    excludes the latest version on PyPI.  A non-zero gap arises when the latest
    satisfying release is older than the absolute latest release.
    """

    def test_should_report_nonzero_gap_for_bounded_range_in_requirements_txt(
        self, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("pandas>=2.0.0,<3.0.0\n")

        releases_map = {
            "pandas": [
                _make_release("3.1.0", "2025-01-01T00:00:00"),
                _make_release("2.0.0", "2023-04-03T00:00:00"),
            ]
        }

        with patch(
            "pip_verv.cli.collect", new_callable=AsyncMock, return_value=releases_map
        ):
            result = runner.invoke(
                app, ["--path", str(tmp_path), "--format", "json", "--no-cache"]
            )

        assert result.exit_code == 0
        dep = json.loads(result.output)["dependencies"][0]
        # declared_version (spec-resolved) = 2.0.0 — verified via gap calculation
        assert dep["days_behind"] is not None
        assert dep["days_behind"] > 0  # 2.0.0 vs 3.1.0

    def test_should_report_nonzero_gap_for_bounded_range_in_pyproject_toml(
        self, tmp_path: Path
    ) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\ndependencies = ["pandas>=2.0.0,<3.0.0"]\n'
        )

        releases_map = {
            "pandas": [
                _make_release("3.1.0", "2025-01-01T00:00:00"),
                _make_release("2.0.0", "2023-04-03T00:00:00"),
            ]
        }

        with patch(
            "pip_verv.cli.collect", new_callable=AsyncMock, return_value=releases_map
        ):
            result = runner.invoke(
                app, ["--path", str(tmp_path), "--format", "json", "--no-cache"]
            )

        assert result.exit_code == 0
        dep = json.loads(result.output)["dependencies"][0]
        assert dep["days_behind"] is not None
        assert dep["days_behind"] > 0

    def test_should_report_nonzero_gap_for_tilde_constraint(
        self, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests~=2.28.0\n")

        releases_map = {
            "requests": [
                _make_release("3.0.0", "2024-06-01T00:00:00"),   # outside ~=2.28.0
                _make_release("2.28.5", "2023-12-01T00:00:00"),  # inside ~=2.28.0
                _make_release("2.28.0", "2022-06-09T00:00:00"),
            ]
        }

        with patch(
            "pip_verv.cli.collect", new_callable=AsyncMock, return_value=releases_map
        ):
            result = runner.invoke(
                app, ["--path", str(tmp_path), "--format", "json", "--no-cache"]
            )

        assert result.exit_code == 0
        dep = json.loads(result.output)["dependencies"][0]
        # ~=2.28.0 resolves 2.28.5; gap to latest 3.0.0 is positive
        assert dep["days_behind"] is not None
        assert dep["days_behind"] > 0  # 2.28.5 vs 3.0.0

    def test_should_show_latest_satisfying_and_zero_gap_when_lb_absent_from_releases(
        self, tmp_path: Path
    ) -> None:
        """When lb version is absent from PyPI, current is still the latest
        satisfying release; gap is 0 when that equals the absolute latest."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("mylib>=2.0.0\n")

        releases_map = {
            # Only has releases newer than 2.0.0 — 2.0.0 itself absent
            "mylib": [
                _make_release("3.5.0", "2025-01-01T00:00:00"),
                _make_release("2.5.0", "2024-01-01T00:00:00"),
            ]
        }

        with patch(
            "pip_verv.cli.collect", new_callable=AsyncMock, return_value=releases_map
        ):
            result = runner.invoke(
                app, ["--path", str(tmp_path), "--format", "json", "--no-cache"]
            )

        assert result.exit_code == 0
        dep = json.loads(result.output)["dependencies"][0]
        # 3.5.0 satisfies >=2.0.0 and equals latest → gap = 0
        assert dep["days_behind"] == 0       # current == latest → no gap

    def test_should_report_zero_gap_for_exact_pin_at_latest(
        self, tmp_path: Path
    ) -> None:
        """Pinned to latest → gap must be exactly 0."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests==2.31.0\n")

        releases_map = {
            "requests": [
                _make_release("2.31.0", "2023-05-22T00:00:00"),
            ]
        }

        with patch(
            "pip_verv.cli.collect", new_callable=AsyncMock, return_value=releases_map
        ):
            result = runner.invoke(
                app, ["--path", str(tmp_path), "--format", "json", "--no-cache"]
            )

        assert result.exit_code == 0
        dep = json.loads(result.output)["dependencies"][0]
        # Pinned to latest → gap must be exactly 0
        assert dep["days_behind"] == 0

    def test_should_report_outdated_when_range_constraint_excludes_latest(
        self, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("flask>=2.0.0,<3.0.0\n")

        releases_map = {
            "flask": [
                _make_release("3.1.0", "2025-01-01T00:00:00"),
                _make_release("2.0.0", "2022-01-01T00:00:00"),
            ]
        }

        with patch(
            "pip_verv.cli.collect", new_callable=AsyncMock, return_value=releases_map
        ):
            result = runner.invoke(
                app, ["--path", str(tmp_path), "--format", "json", "--no-cache"]
            )

        assert result.exit_code == 0
        dep = json.loads(result.output)["dependencies"][0]
        assert dep["status"] == "outdated"
        assert dep["days_behind"] is not None
        assert dep["days_behind"] > 0


class TestAuditCommandBlockerDetection:
    """Blockers must be computed whenever the installed version lags behind latest,
    even when the user's own requirement spec would allow the latest version."""

    def test_should_find_blockers_when_installed_lags_despite_open_spec(
        self, tmp_path: Path
    ) -> None:
        # Spec allows latest (>=2.0.0 includes 3.0.2) but installed=2.3.3
        # because another package (streamlit) constrains it to <3.
        # The real status is OUTDATED because installed != latest.
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("pandas>=2.0.0\n")

        releases_map = {
            "pandas": [
                _make_release("3.0.2", "2025-01-01T00:00:00"),
                _make_release("2.3.3", "2024-06-01T00:00:00"),
                _make_release("2.0.0", "2023-01-01T00:00:00"),
            ]
        }

        with (
            patch(
                "pip_verv.cli.collect",
                new_callable=AsyncMock,
                return_value=releases_map,
            ),
            patch(
                "pip_verv.cli.get_installed_packages",
                return_value={"pandas": "2.3.3", "streamlit": "1.43.0"},
            ),
            patch(
                "pip_verv.cli.find_blockers",
                return_value=["streamlit (<3,>=1.4.0)"],
            ) as mock_find_blockers,
            patch(
                "pip_verv.cli.find_installable_version",
                return_value="2.3.3",
            ),
        ):
            result = runner.invoke(
                app, ["--path", str(tmp_path), "--format", "json", "--no-cache"]
            )

        assert result.exit_code == 0
        dep = json.loads(result.output)["dependencies"][0]
        # installed (2.3.3) != latest (3.0.2) → status must be outdated
        assert dep["status"] == "outdated"
        # Blockers populated because installed lags behind latest
        assert dep["blockers"] == ["streamlit (<3,>=1.4.0)"]
        # blocked at ceiling (installable == installed) → target null
        assert dep["target"] is None
        mock_find_blockers.assert_called_once_with(
            "pandas", "3.0.2", {"pandas": "2.3.3", "streamlit": "1.43.0"}
        )

    def test_should_not_call_find_blockers_when_installed_matches_latest(
        self, tmp_path: Path
    ) -> None:
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests>=2.28.0\n")

        with (
            patch(
                "pip_verv.cli.collect",
                new_callable=AsyncMock,
                return_value=_make_releases_map(),
            ),
            patch(
                "pip_verv.cli.get_installed_packages",
                # installed matches the latest available release
                return_value={"requests": "2.31.0"},
            ),
            patch("pip_verv.cli.find_blockers", return_value=[]) as mock_find_blockers,
        ):
            result = runner.invoke(
                app, ["--path", str(tmp_path), "--format", "json", "--no-cache"]
            )

        assert result.exit_code == 0
        # find_blockers must NOT be called because installed == latest
        mock_find_blockers.assert_not_called()

    def test_should_set_installable_to_latest_when_outdated_and_no_blockers(
        self, tmp_path: Path
    ) -> None:
        """When an outdated package has no env-constraint blockers, installable
        should equal the latest available version (not null)."""
        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests>=2.28.0\n")

        releases_map = {
            "requests": [
                _make_release("2.31.0", "2024-01-01T00:00:00"),
                _make_release("2.28.0", "2022-01-01T00:00:00"),
            ]
        }

        with (
            patch(
                "pip_verv.cli.collect",
                new_callable=AsyncMock,
                return_value=releases_map,
            ),
            patch(
                "pip_verv.cli.get_installed_packages",
                return_value={"requests": "2.28.0"},
            ),
            patch("pip_verv.cli.find_blockers", return_value=[]),
        ):
            result = runner.invoke(
                app, ["--path", str(tmp_path), "--format", "json", "--no-cache"]
            )

        assert result.exit_code == 0
        dep = json.loads(result.output)["dependencies"][0]
        assert dep["status"] == "outdated"
        # No env blockers → target = latest (can upgrade freely)
        assert dep["target"] == dep["latest"]
        assert dep["target"] == "2.31.0"
