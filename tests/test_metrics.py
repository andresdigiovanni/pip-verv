import datetime

import pytest

from pip_verv.metrics import compute_gap, compute_score
from pip_verv.models import (
    AuditResult,
    Dependency,
    PackageRelease,
    Severity,
    Status,
)


def _make_dep(name: str = "pkg") -> Dependency:
    return Dependency(name=name, version_spec=">=1.0", source="req.txt")


def _make_release(version: str, date_str: str) -> PackageRelease:
    return PackageRelease(
        version=version,
        release_date=datetime.datetime.fromisoformat(date_str),
        yanked=False,
    )


def _make_result(
    dep: Dependency | None = None,
    declared_version: str | None = None,
    installed_version: str | None = None,
    latest_version: str | None = None,
    gap_days: int | None = None,
    severity: Severity = Severity.NA,
    status: Status = Status.UP_TO_DATE,
) -> AuditResult:
    return AuditResult(
        dependency=dep or _make_dep(),
        declared_version=declared_version,
        installed_version=installed_version,
        latest_version=latest_version,
        gap_days=gap_days,
        severity=severity,
        status=status,
        latest_release_date=None,
        declared_release_date=None,
    )


class TestComputeGap:
    def test_should_return_severity_na_when_declared_version_is_none(self) -> None:
        result = _make_result(declared_version=None, latest_version="2.31.0")

        updated = compute_gap(result, [])

        assert updated.severity == Severity.NA
        assert updated.gap_days is None

    def test_should_return_severity_na_when_neither_declared_nor_installed(
        self,
    ) -> None:
        result = _make_result(
            declared_version=None, installed_version=None, latest_version="2.31.0"
        )

        updated = compute_gap(result, [])

        assert updated.severity == Severity.NA
        assert updated.gap_days is None

    def test_should_return_severity_na_when_latest_version_is_none(self) -> None:
        result = _make_result(declared_version="2.28.0", latest_version=None)

        updated = compute_gap(result, [])

        assert updated.severity == Severity.NA
        assert updated.gap_days is None

    def test_should_return_severity_na_when_declared_version_not_in_releases(
        self,
    ) -> None:
        result = _make_result(declared_version="1.0.0", latest_version="2.0.0")
        releases = [_make_release("2.0.0", "2023-01-01T00:00:00")]

        updated = compute_gap(result, releases)

        assert updated.severity == Severity.NA

    def test_should_compute_zero_gap_when_declared_equals_latest(self) -> None:
        result = _make_result(declared_version="2.28.0", latest_version="2.28.0")
        releases = [_make_release("2.28.0", "2022-06-09T10:00:00")]

        updated = compute_gap(result, releases)

        assert updated.gap_days == 0
        assert updated.severity == Severity.NA
        assert updated.upgrade_type is None

    @pytest.mark.parametrize(
        "gap_days_delta,expected_severity",
        [
            (90, Severity.PATCH),
            (91, Severity.MINOR),
            (365, Severity.MINOR),
            (366, Severity.MAJOR),
        ],
    )
    def test_should_assign_correct_severity_for_gap_boundary(
        self,
        gap_days_delta: int,
        expected_severity: Severity,
    ) -> None:
        base_date = datetime.datetime(2022, 1, 1)
        latest_date = base_date + datetime.timedelta(days=gap_days_delta)
        # Use a major version bump so semver cap does not interfere with boundary
        result = _make_result(declared_version="1.0.0", latest_version="2.0.0")
        releases = [
            PackageRelease(version="1.0.0", release_date=base_date, yanked=False),
            PackageRelease(version="2.0.0", release_date=latest_date, yanked=False),
        ]

        updated = compute_gap(result, releases)

        assert updated.severity == expected_severity
        assert updated.gap_days == gap_days_delta

    def test_should_cap_severity_at_patch_when_semver_jump_is_patch(self) -> None:
        """A patch-level version bump cannot be MAJOR-severity (the tqdm case)."""
        # gap=435 days would be MAJOR by time alone; but 4.67.1→4.67.3 is patch
        result = _make_result(
            declared_version="4.67.1", latest_version="4.67.3"
        )
        releases = [
            _make_release("4.67.1", "2023-01-01T00:00:00"),
            _make_release("4.67.3", "2024-03-12T00:00:00"),  # ~435 days later
        ]

        updated = compute_gap(result, releases)

        assert updated.severity == Severity.PATCH  # capped by semver
        assert updated.upgrade_type == "patch"
        assert updated.gap_days == 436  # actual time gap still recorded

    def test_should_cap_severity_at_minor_when_semver_jump_is_minor(self) -> None:
        """A minor version bump caps severity at MINOR even with large time gap."""
        result = _make_result(declared_version="1.2.0", latest_version="1.3.0")
        releases = [
            _make_release("1.2.0", "2021-01-01T00:00:00"),
            _make_release("1.3.0", "2023-01-01T00:00:00"),  # ~730 days → MAJOR by time
        ]

        updated = compute_gap(result, releases)

        assert updated.severity == Severity.MINOR  # capped by semver
        assert updated.upgrade_type == "minor"

    def test_should_set_upgrade_type_major_for_major_version_bump(self) -> None:
        result = _make_result(declared_version="2.0.0", latest_version="3.0.0")
        releases = [
            _make_release("2.0.0", "2023-01-01T00:00:00"),
            _make_release("3.0.0", "2024-01-01T00:00:00"),
        ]

        updated = compute_gap(result, releases)

        assert updated.upgrade_type == "major"
        # ~365 days by time (MINOR), but major semver → min = MINOR
        assert updated.severity == Severity.MINOR


class TestComputeScore:
    def test_should_return_100_for_empty_results(self) -> None:
        score = compute_score([])

        assert score == 100.0

    def test_should_return_100_when_all_results_are_na(self) -> None:
        results = [
            _make_result(severity=Severity.NA),
            _make_result(severity=Severity.NA),
        ]

        score = compute_score(results)

        assert score == 100.0

    def test_should_return_100_when_all_gap_days_are_zero(self) -> None:
        results = [
            _make_result(severity=Severity.PATCH, gap_days=0),
            _make_result(severity=Severity.PATCH, gap_days=0),
        ]

        score = compute_score(results)

        assert score == 100.0

    def test_should_approach_zero_for_single_major_dep_with_extreme_gap(self) -> None:
        results = [
            _make_result(severity=Severity.MAJOR, gap_days=1825),
        ]

        score = compute_score(results)

        # 1825d >> 365d ceiling for MAJOR → score clamped to 0
        assert score == pytest.approx(0.0, abs=0.01)

    def test_should_score_lower_for_major_than_for_patch_at_same_gap(
        self,
    ) -> None:
        major = [_make_result(severity=Severity.MAJOR, gap_days=180)]
        patch = [_make_result(severity=Severity.PATCH, gap_days=180)]

        assert compute_score(major) < compute_score(patch)

    def test_should_improve_score_when_up_to_date_packages_present(self) -> None:
        outdated_only = [_make_result(severity=Severity.MINOR, gap_days=365)]
        with_up_to_date = [
            _make_result(severity=Severity.MINOR, gap_days=365),
            _make_result(severity=Severity.NA, gap_days=0),  # confirmed up-to-date
        ]

        score_outdated = compute_score(outdated_only)
        score_mixed = compute_score(with_up_to_date)

        # Up-to-date packages contribute 100%, raising the average
        assert score_mixed > score_outdated

    def test_should_return_score_between_0_and_100_for_mixed_severities(
        self,
    ) -> None:
        results = [
            _make_result(severity=Severity.MAJOR, gap_days=400),
            _make_result(severity=Severity.MINOR, gap_days=120),
            _make_result(severity=Severity.PATCH, gap_days=30),
        ]

        score = compute_score(results)

        assert 0.0 < score < 100.0

    def test_should_score_100_when_na_and_zero_gap_mixed(self) -> None:
        results = [
            _make_result(severity=Severity.NA),
            _make_result(severity=Severity.PATCH, gap_days=0),
        ]

        score = compute_score(results)

        assert score == 100.0


# ---------------------------------------------------------------------------
# Integration: compute_gap + compute_score pipeline for range constraints
# ---------------------------------------------------------------------------


class TestComputeGapForRangeConstraints:
    """Verify that the gap pipeline correctly handles the lower-bound scenario
    produced by the analyzer for range constraints."""

    def test_should_compute_positive_gap_when_lb_version_exists_in_releases(
        self,
    ) -> None:
        """Simulates analyzer returning the lower bound as declared_version."""
        result = _make_result(
            declared_version="2.0.0",
            latest_version="3.0.0",
            status=Status.UP_TO_DATE,
        )
        releases = [
            _make_release("3.0.0", "2025-01-01T00:00:00"),
            _make_release("2.0.0", "2023-01-01T00:00:00"),
        ]

        updated = compute_gap(result, releases)

        assert updated.gap_days is not None
        assert updated.gap_days > 0
        assert updated.severity != Severity.NA

    def test_should_return_na_gap_when_declared_version_is_none_from_range(
        self,
    ) -> None:
        """When the analyzer cannot find the lb in releases, declared=None.
        compute_gap must return NA (not 0 — that would hide the uncertainty)."""
        result = _make_result(
            declared_version=None,
            latest_version="3.5.0",
            status=Status.UP_TO_DATE,
        )
        releases = [_make_release("3.5.0", "2025-01-01T00:00:00")]

        updated = compute_gap(result, releases)

        assert updated.gap_days is None
        assert updated.severity == Severity.NA

    def test_should_preserve_outdated_status_when_range_excludes_latest(
        self,
    ) -> None:
        """compute_gap should not change the status set by the analyzer."""
        result = _make_result(
            declared_version="2.0.0",
            latest_version="3.0.0",
            status=Status.OUTDATED,
        )
        releases = [
            _make_release("3.0.0", "2025-01-01T00:00:00"),
            _make_release("2.0.0", "2022-01-01T00:00:00"),
        ]

        updated = compute_gap(result, releases)

        assert updated.status == Status.OUTDATED
        assert updated.gap_days is not None
        assert updated.gap_days > 0

    def test_should_use_installed_version_when_available(self) -> None:
        """Gap should be installed→latest, not declared→latest."""
        result = _make_result(
            declared_version="3.0.0",   # spec-resolved (open spec allows latest)
            installed_version="2.3.3",  # actually installed (another pkg constrains)
            latest_version="3.0.2",
            status=Status.OUTDATED,
        )
        releases = [
            _make_release("3.0.2", "2025-01-01T00:00:00"),
            _make_release("2.3.3", "2024-06-01T00:00:00"),
            _make_release("3.0.0", "2024-10-01T00:00:00"),
        ]

        updated = compute_gap(result, releases)

        # Gap must be 3.0.2 release date minus 2.3.3 release date, not 3.0.0
        expected_days = (
            datetime.datetime(2025, 1, 1) - datetime.datetime(2024, 6, 1)
        ).days
        assert updated.gap_days == expected_days

    def test_should_fall_back_to_declared_version_when_installed_not_set(self) -> None:
        """When installed_version is None, declared_version is used for the gap."""
        result = _make_result(
            declared_version="2.0.0",
            installed_version=None,
            latest_version="3.0.0",
            status=Status.OUTDATED,
        )
        releases = [
            _make_release("3.0.0", "2025-01-01T00:00:00"),
            _make_release("2.0.0", "2023-01-01T00:00:00"),
        ]

        updated = compute_gap(result, releases)

        expected_days = (
            datetime.datetime(2025, 1, 1) - datetime.datetime(2023, 1, 1)
        ).days
        assert updated.gap_days == expected_days


class TestComputeScoreWithMixedConstraintTypes:
    """Score must correctly handle the NA results that arise from range
    constraints whose lower bound is absent from PyPI."""

    def test_should_exclude_na_from_score_when_lb_absent(self) -> None:
        """A range dep with severity=NA must contribute zero penalties.
        Using a PATCH dep with gap=0 makes the expected score exactly 100."""
        results = [
            _make_result(severity=Severity.NA, status=Status.UP_TO_DATE),
            _make_result(severity=Severity.PATCH, gap_days=0),
        ]

        score = compute_score(results)

        assert score == 100.0  # NA contributes nothing; gap=0 PATCH too

    def test_should_penalise_pinned_outdated_dep_alongside_na_range_dep(
        self,
    ) -> None:
        """An outdated pinned dep should reduce the score even when other deps
        have NA severity — NA must not affect the calculation."""
        results = [
            _make_result(severity=Severity.NA),
            _make_result(severity=Severity.MAJOR, gap_days=400),
        ]
        results_major_only = [_make_result(severity=Severity.MAJOR, gap_days=400)]

        score_mixed = compute_score(results)
        score_major_only = compute_score(results_major_only)

        assert score_mixed == pytest.approx(score_major_only, abs=0.01)


# ---------------------------------------------------------------------------
# Pre-release and post-release declared versions
# ---------------------------------------------------------------------------


class TestComputeGapPreAndPostRelease:
    """Pre-releases are filtered out of the releases list by the collector, so
    a declared_version that is a pre-release string will never be found →
    compute_gap must return NA.

    Post-releases are NOT pre-releases per PEP 440 (is_prerelease=False), so
    they ARE in the releases list and gap is computable.
    """

    def test_should_return_na_when_declared_version_is_rc(self) -> None:
        """declared='2.0.0rc1' is never in releases (pre-releases filtered)."""
        result = _make_result(declared_version="2.0.0rc1", latest_version="2.0.0")
        releases = [_make_release("2.0.0", "2024-01-01T00:00:00")]

        updated = compute_gap(result, releases)

        assert updated.severity == Severity.NA
        assert updated.gap_days is None

    def test_should_return_na_when_declared_version_is_alpha(self) -> None:
        result = _make_result(declared_version="1.0.0a1", latest_version="1.0.0")
        releases = [_make_release("1.0.0", "2024-01-01T00:00:00")]

        updated = compute_gap(result, releases)

        assert updated.severity == Severity.NA
        assert updated.gap_days is None

    def test_should_return_na_when_declared_version_is_dev(self) -> None:
        result = _make_result(declared_version="1.0.0.dev1", latest_version="1.0.0")
        releases = [_make_release("1.0.0", "2024-01-01T00:00:00")]

        updated = compute_gap(result, releases)

        assert updated.severity == Severity.NA
        assert updated.gap_days is None

    def test_should_compute_gap_for_post_release_declared_version(self) -> None:
        """Post-releases are stable per PEP 440 → included in releases → gap OK."""
        result = _make_result(
            declared_version="2.28.0.post1",
            latest_version="2.31.0",
        )
        releases = [
            _make_release("2.31.0", "2023-05-22T00:00:00"),
            _make_release("2.28.0.post1", "2022-06-15T00:00:00"),
            _make_release("2.28.0", "2022-06-09T00:00:00"),
        ]

        updated = compute_gap(result, releases)

        assert updated.gap_days is not None
        assert updated.gap_days > 0
        assert updated.severity != Severity.NA

    def test_should_normalise_version_string_for_find_release(self) -> None:
        """'2.28' in declared should match release stored as '2.28.0' via
        Version() equality (not string equality)."""
        result = _make_result(declared_version="2.28", latest_version="2.31.0")
        releases = [
            _make_release("2.31.0", "2023-05-22T00:00:00"),
            _make_release("2.28.0", "2022-06-09T00:00:00"),  # stored as '2.28.0'
        ]

        updated = compute_gap(result, releases)

        # '2.28' matches '2.28.0' via Version() → gap computable
        assert updated.gap_days is not None
        assert updated.gap_days > 0
