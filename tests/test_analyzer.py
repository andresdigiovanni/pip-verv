import datetime

import pytest

from pip_verv.analyzer import analyze
from pip_verv.models import Dependency, PackageRelease, Status


def _make_dep(name: str, spec: str, auditable: bool = True) -> Dependency:
    return Dependency(
        name=name, version_spec=spec, source="req.txt", is_auditable=auditable
    )


def _make_releases(*versions_and_dates: tuple[str, str]) -> list[PackageRelease]:
    return [
        PackageRelease(
            version=v,
            release_date=datetime.datetime.fromisoformat(d),
            yanked=False,
        )
        for v, d in versions_and_dates
    ]


class TestAnalyze:
    def test_should_be_up_to_date_when_exact_pin_matches_latest(self) -> None:
        dep = _make_dep("requests", "==2.28.0")
        releases = _make_releases(("2.28.0", "2022-06-09T10:00:00"))

        declared, status = analyze(dep, releases)

        assert declared == "2.28.0"
        assert status == Status.UP_TO_DATE

    def test_should_be_outdated_when_exact_pin_is_behind_latest(self) -> None:
        dep = _make_dep("requests", "==2.28.0")
        releases = _make_releases(
            ("2.31.0", "2023-05-22T15:00:00"),
            ("2.28.0", "2022-06-09T10:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert declared == "2.28.0"
        assert status == Status.OUTDATED

    def test_should_be_up_to_date_when_range_includes_latest(self) -> None:
        dep = _make_dep("requests", ">=2.0,<3.0")
        releases = _make_releases(
            ("2.31.0", "2023-05-22T15:00:00"),
            ("2.28.0", "2022-06-09T10:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert status == Status.UP_TO_DATE

    def test_should_be_outdated_when_range_excludes_latest(self) -> None:
        dep = _make_dep("requests", ">=2.0,<3.0")
        releases = _make_releases(
            ("3.1.0", "2024-01-01T00:00:00"),
            ("2.31.0", "2023-05-22T15:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert status == Status.OUTDATED

    def test_should_return_not_auditable_when_dep_is_not_auditable(self) -> None:
        dep = _make_dep("mylib", "", auditable=False)
        releases = _make_releases(("1.0.0", "2023-01-01T00:00:00"))

        declared, status = analyze(dep, releases)

        assert declared is None
        assert status == Status.NOT_AUDITABLE

    def test_should_return_no_data_when_releases_empty(self) -> None:
        dep = _make_dep("requests", ">=2.0")

        declared, status = analyze(dep, [])

        assert declared is None
        assert status == Status.NO_DATA

    def test_should_return_latest_satisfying_for_compatible_release_operator(
        self,
    ) -> None:
        dep = _make_dep("requests", "~=2.28")
        releases = _make_releases(
            ("2.31.0", "2023-05-22T15:00:00"),
            ("2.28.0", "2022-06-09T10:00:00"),
            ("3.0.0", "2024-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        # ~=2.28 -> >=2.28, <3; latest satisfying is 2.31.0;
        # overall latest 3.0.0 is outside
        assert declared == "2.31.0"
        assert status == Status.OUTDATED

    def test_should_return_none_when_constraint_excludes_all_available_releases(
        self,
    ) -> None:
        dep = _make_dep("requests", ">=999")
        releases = _make_releases(("2.31.0", "2023-05-22T15:00:00"))

        declared, status = analyze(dep, releases)

        assert declared is None
        assert status == Status.OUTDATED

    @pytest.mark.parametrize(
        "spec,versions,expected_declared",
        [
            (
                ">=2.0,<3.0",
                [("2.0.0", "2020-01-01T00:00:00"), ("2.31.0", "2023-01-01T00:00:00")],
                "2.31.0",
            ),
            (
                ">=2.28.0",
                [("2.28.0", "2022-01-01T00:00:00"), ("2.31.0", "2023-01-01T00:00:00")],
                "2.31.0",
            ),
        ],
    )
    def test_should_use_latest_satisfying_version_for_range_constraints(
        self,
        spec: str,
        versions: list[tuple[str, str]],
        expected_declared: str,
    ) -> None:
        dep = _make_dep("pkg", spec)
        releases = _make_releases(*versions)

        declared, _ = analyze(dep, releases)

        assert declared == expected_declared


# ---------------------------------------------------------------------------
# >= (minimum bound) — exhaustive cases
# ---------------------------------------------------------------------------


class TestAnalyzeMinimumBoundConstraint:
    """All scenarios for the most common constraint type: >=X.Y.Z"""

    def test_should_return_latest_satisfying_for_ge_constraint(
        self,
    ) -> None:
        dep = _make_dep("pkg", ">=2.0.0")
        releases = _make_releases(
            ("3.5.0", "2025-01-01T00:00:00"),
            ("2.0.0", "2022-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert declared == "3.5.0"
        assert status == Status.UP_TO_DATE

    def test_should_return_latest_satisfying_when_lb_absent_from_releases(
        self,
    ) -> None:
        dep = _make_dep("pkg", ">=2.0.0")
        releases = _make_releases(
            ("3.5.0", "2025-01-01T00:00:00"),
            ("2.5.0", "2024-01-01T00:00:00"),
            # 2.0.0 intentionally absent
        )

        declared, status = analyze(dep, releases)

        assert declared == "3.5.0"
        assert status == Status.UP_TO_DATE

    def test_should_return_latest_satisfying_for_two_part_notation(self) -> None:
        dep = _make_dep("pkg", ">=2.0")
        releases = _make_releases(
            ("3.0.0", "2024-01-01T00:00:00"),
            ("2.0.0", "2022-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert declared == "3.0.0"
        assert status == Status.UP_TO_DATE

    def test_should_return_latest_overall_when_it_satisfies_ge_constraint(self) -> None:
        dep = _make_dep("pkg", ">=1.0.0")
        releases = _make_releases(
            ("99.0.0", "2025-01-01T00:00:00"),
            ("1.0.0", "2010-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert declared == "99.0.0"
        assert status == Status.UP_TO_DATE


# ---------------------------------------------------------------------------
# >= X,< Y (bounded range) — exhaustive cases
# ---------------------------------------------------------------------------


class TestAnalyzeBoundedRangeConstraint:
    """>=X.Y.Z,<A.B.C combinations."""

    def test_should_return_latest_inside_range_when_latest_satisfies(self) -> None:
        dep = _make_dep("pkg", ">=2.0.0,<3.0.0")
        releases = _make_releases(
            ("2.9.0", "2024-01-01T00:00:00"),
            ("2.0.0", "2022-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert declared == "2.9.0"
        assert status == Status.UP_TO_DATE

    def test_should_return_latest_satisfying_when_latest_breaks_upper_bound(
        self,
    ) -> None:
        dep = _make_dep("pkg", ">=2.0.0,<3.0.0")
        releases = _make_releases(
            ("3.1.0", "2025-01-01T00:00:00"),
            ("2.0.0", "2022-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        # Only 2.0.0 satisfies >=2.0.0,<3.0.0 (3.1.0 breaks upper bound)
        assert declared == "2.0.0"
        assert status == Status.OUTDATED

    def test_should_return_latest_satisfying_when_lb_absent_latest_inside_range(
        self,
    ) -> None:
        dep = _make_dep("pkg", ">=2.0.0,<3.0.0")
        releases = _make_releases(
            ("2.5.0", "2024-01-01T00:00:00"),
            # 2.0.0 absent
        )

        declared, status = analyze(dep, releases)

        assert declared == "2.5.0"
        assert status == Status.UP_TO_DATE

    def test_should_return_none_when_no_release_satisfies_range(
        self,
    ) -> None:
        dep = _make_dep("pkg", ">=2.0.0,<3.0.0")
        releases = _make_releases(
            ("3.0.0", "2025-01-01T00:00:00"),
            # 3.0.0 is not < 3.0.0 -> no release satisfies the range
        )

        declared, status = analyze(dep, releases)

        assert declared is None
        assert status == Status.OUTDATED


# ---------------------------------------------------------------------------
# ~= (compatible release) — exhaustive cases
# ---------------------------------------------------------------------------


class TestAnalyzeCompatibleReleaseConstraint:
    """~=X.Y (minor-level) and ~=X.Y.Z (patch-level) cases."""

    def test_should_return_latest_satisfying_for_minor_compatible_release(
        self,
    ) -> None:
        dep = _make_dep("pkg", "~=2.28")
        releases = _make_releases(
            ("2.31.0", "2023-06-01T00:00:00"),
            ("2.28.0", "2022-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        # ~=2.28 equiv >=2.28, <3; latest satisfying is 2.31.0
        assert declared == "2.31.0"
        assert status == Status.UP_TO_DATE

    def test_should_return_latest_satisfying_for_patch_compatible_release(
        self,
    ) -> None:
        dep = _make_dep("pkg", "~=2.28.0")
        releases = _make_releases(
            ("2.28.5", "2023-01-01T00:00:00"),
            ("2.28.0", "2022-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        # ~=2.28.0 equiv >=2.28.0, <2.29; latest satisfying is 2.28.5
        assert declared == "2.28.5"
        assert status == Status.UP_TO_DATE

    def test_should_return_only_satisfying_when_major_bump_breaks_compatible_release(
        self,
    ) -> None:
        dep = _make_dep("pkg", "~=2.28")
        releases = _make_releases(
            ("3.0.0", "2024-06-01T00:00:00"),
            ("2.28.0", "2022-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        # 3.0.0 breaks ~=2.28 (<3); only 2.28.0 satisfies
        assert declared == "2.28.0"
        assert status == Status.OUTDATED

    def test_should_return_latest_satisfying_when_tilde_lb_absent_from_releases(
        self,
    ) -> None:
        dep = _make_dep("pkg", "~=2.28.0")
        releases = _make_releases(
            ("2.28.5", "2023-01-01T00:00:00"),
            # 2.28.0 absent
        )

        declared, status = analyze(dep, releases)

        # 2.28.5 satisfies ~=2.28.0 (>=2.28.0, <2.29)
        assert declared == "2.28.5"
        assert status == Status.UP_TO_DATE


# ---------------------------------------------------------------------------
# Upper-bound only: <X.Y.Z / <=X.Y.Z
# ---------------------------------------------------------------------------


class TestAnalyzeUpperBoundOnlyConstraint:
    """No explicit lower bound; current is latest release satisfying the constraint."""

    def test_should_return_latest_satisfying_for_strict_upper_bound(self) -> None:
        dep = _make_dep("pkg", "<3.0.0")
        releases = _make_releases(("2.9.0", "2024-01-01T00:00:00"))

        declared, status = analyze(dep, releases)

        assert declared == "2.9.0"

    def test_should_be_up_to_date_when_latest_satisfies_strict_upper_bound(
        self,
    ) -> None:
        dep = _make_dep("pkg", "<3.0.0")
        releases = _make_releases(("2.9.0", "2024-01-01T00:00:00"))

        _, status = analyze(dep, releases)

        assert status == Status.UP_TO_DATE

    def test_should_be_outdated_when_latest_exceeds_strict_upper_bound(self) -> None:
        dep = _make_dep("pkg", "<3.0.0")
        releases = _make_releases(("3.1.0", "2025-01-01T00:00:00"))

        _, status = analyze(dep, releases)

        assert status == Status.OUTDATED

    def test_should_return_latest_satisfying_for_inclusive_upper_bound(self) -> None:
        dep = _make_dep("pkg", "<=3.0.0")
        releases = _make_releases(("3.0.0", "2024-01-01T00:00:00"))

        declared, status = analyze(dep, releases)

        assert declared == "3.0.0"
        assert status == Status.UP_TO_DATE

    def test_should_be_outdated_when_latest_exceeds_inclusive_upper_bound(
        self,
    ) -> None:
        dep = _make_dep("pkg", "<=3.0.0")
        releases = _make_releases(("3.1.0", "2025-01-01T00:00:00"))

        _, status = analyze(dep, releases)

        assert status == Status.OUTDATED


# ---------------------------------------------------------------------------
# Exclusion only: !=X.Y.Z
# ---------------------------------------------------------------------------


class TestAnalyzeExclusionConstraint:
    """!= constraint; current is the latest release not excluded."""

    def test_should_return_latest_non_excluded_for_exclusion_only(self) -> None:
        dep = _make_dep("pkg", "!=2.29.0")
        releases = _make_releases(("2.31.0", "2023-01-01T00:00:00"))

        declared, _ = analyze(dep, releases)

        assert declared == "2.31.0"

    def test_should_be_up_to_date_when_latest_is_not_excluded(self) -> None:
        dep = _make_dep("pkg", "!=2.29.0")
        releases = _make_releases(("2.31.0", "2023-01-01T00:00:00"))

        _, status = analyze(dep, releases)

        assert status == Status.UP_TO_DATE

    def test_should_be_outdated_when_latest_is_the_excluded_version(self) -> None:
        """All available releases are the excluded one → constraint unsatisfiable."""
        dep = _make_dep("pkg", "!=2.31.0")
        releases = _make_releases(("2.31.0", "2023-01-01T00:00:00"))

        _, status = analyze(dep, releases)

        assert status == Status.OUTDATED

    def test_should_return_latest_satisfying_with_combined_ge_ne(self) -> None:
        dep = _make_dep("pkg", ">=2.0.0,!=2.5.0")
        releases = _make_releases(
            ("3.0.0", "2025-01-01T00:00:00"),
            ("2.0.0", "2022-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert declared == "3.0.0"
        assert status == Status.UP_TO_DATE


# ---------------------------------------------------------------------------
# Strict-greater: >X.Y.Z  — excluded version, NOT a valid baseline
# ---------------------------------------------------------------------------


class TestAnalyzeStrictGreaterConstraint:
    """>X.Y.Z -- current is the latest release strictly greater than X.Y.Z."""

    def test_should_return_latest_satisfying_for_strict_greater(
        self,
    ) -> None:
        dep = _make_dep("pkg", ">2.0.0")
        releases = _make_releases(
            ("3.0.0", "2024-01-01T00:00:00"),
            ("2.0.0", "2022-01-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert declared == "3.0.0"
        assert status == Status.UP_TO_DATE

    def test_should_be_outdated_when_latest_does_not_satisfy_strict_greater(
        self,
    ) -> None:
        """All releases are exactly X.Y.Z → none satisfy >X.Y.Z."""
        dep = _make_dep("pkg", ">3.0.0")
        releases = _make_releases(("3.0.0", "2024-01-01T00:00:00"))

        _, status = analyze(dep, releases)

        assert status == Status.OUTDATED


# ---------------------------------------------------------------------------
# Empty / unconstrained spec
# ---------------------------------------------------------------------------


class TestAnalyzeEmptyConstraint:
    """An empty spec accepts every version; current is the latest release."""

    def test_should_return_latest_for_empty_spec(self) -> None:
        dep = _make_dep("pkg", "")
        releases = _make_releases(("2.31.0", "2023-01-01T00:00:00"))

        declared, _ = analyze(dep, releases)

        assert declared == "2.31.0"

    def test_should_always_be_up_to_date_for_empty_spec(self) -> None:
        dep = _make_dep("pkg", "")
        releases = _make_releases(("99.0.0", "2025-01-01T00:00:00"))

        _, status = analyze(dep, releases)

        assert status == Status.UP_TO_DATE


# ---------------------------------------------------------------------------
# Wildcard pin: ==X.Y.*
# ---------------------------------------------------------------------------


class TestAnalyzeWildcardPin:
    """==X.Y.* -- current is the latest release in the X.Y.x series on PyPI."""

    def test_should_return_latest_in_series_for_wildcard_pin(self) -> None:
        dep = _make_dep("pkg", "==2.28.*")
        releases = _make_releases(("2.28.5", "2023-01-01T00:00:00"))

        declared, _ = analyze(dep, releases)

        assert declared == "2.28.5"

    def test_should_be_up_to_date_when_latest_matches_wildcard_series(self) -> None:
        dep = _make_dep("pkg", "==2.28.*")
        releases = _make_releases(("2.28.5", "2023-01-01T00:00:00"))

        _, status = analyze(dep, releases)

        assert status == Status.UP_TO_DATE

    def test_should_be_outdated_when_latest_is_outside_wildcard_series(self) -> None:
        """Latest 3.0.0 is not in ==2.28.* (series 2.28.x only)."""
        dep = _make_dep("pkg", "==2.28.*")
        releases = _make_releases(
            ("3.0.0", "2025-01-01T00:00:00"),
            ("2.28.9", "2023-06-01T00:00:00"),
        )

        # latest by DATE is 3.0.0; 3.0.0 not in ==2.28.*
        _, status = analyze(dep, releases)

        assert status == Status.OUTDATED


# ---------------------------------------------------------------------------
# Pre-release and dev version declarations
# ---------------------------------------------------------------------------


class TestAnalyzePreReleaseDeclared:
    """Pre-release specifiers.

    The collector ALWAYS filters pre-releases from the releases list.
    An exact pre-release pin (==X.Y.ZrcN) will never match any stable
    release, so current is None and compute_gap returns NA.
    A range constraint like >=X.Y.ZrcN can still be satisfied by stable
    releases newer than the pre-release.
    """

    def test_should_return_none_for_exact_rc_pin_with_no_matching_stable(
        self,
    ) -> None:
        dep = _make_dep("pkg", "==2.0.0rc1")
        releases = _make_releases(("2.0.0", "2024-01-01T00:00:00"))

        declared, status = analyze(dep, releases)

        assert declared is None
        assert status == Status.OUTDATED  # stable 2.0.0 != ==2.0.0rc1

    def test_should_return_none_for_exact_alpha_pin_with_no_matching_stable(
        self,
    ) -> None:
        dep = _make_dep("pkg", "==1.0.0a1")
        releases = _make_releases(("1.0.0", "2024-01-01T00:00:00"))

        declared, status = analyze(dep, releases)

        assert declared is None
        assert status == Status.OUTDATED

    def test_should_return_none_for_exact_dev_pin_with_no_matching_stable(
        self,
    ) -> None:
        dep = _make_dep("pkg", "==1.0.0.dev1")
        releases = _make_releases(("1.0.0", "2024-01-01T00:00:00"))

        declared, status = analyze(dep, releases)

        assert declared is None
        assert status == Status.OUTDATED

    def test_should_return_latest_stable_satisfying_ge_rc_constraint(self) -> None:
        """>=2.0.0rc1: stable 2.0.0 satisfies because 2.0.0 > 2.0.0rc1."""
        dep = _make_dep("pkg", ">=2.0.0rc1")
        releases = _make_releases(("2.0.0", "2024-01-01T00:00:00"))

        declared, status = analyze(dep, releases)

        assert declared == "2.0.0"
        assert status == Status.UP_TO_DATE


# ---------------------------------------------------------------------------
# Post-release declarations
# ---------------------------------------------------------------------------


class TestAnalyzePostReleaseDeclared:
    """Post-releases (X.Y.Z.post1) are NOT pre-releases per PEP 440.
    The collector includes them in the releases list.
    They can appear as declared_version and have a release date for GAP computation.
    """

    def test_should_use_post_release_as_declared_for_exact_post_pin(self) -> None:
        dep = _make_dep("pkg", "==2.28.0.post1")
        releases = _make_releases(
            ("2.28.0.post1", "2022-06-15T00:00:00"),
            ("2.28.0", "2022-06-09T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert declared == "2.28.0.post1"
        assert status == Status.UP_TO_DATE  # latest by date is 2.28.0.post1

    def test_should_be_outdated_when_newer_release_exists_after_post_pin(
        self,
    ) -> None:
        dep = _make_dep("pkg", "==2.28.0.post1")
        releases = _make_releases(
            ("2.31.0", "2023-05-01T00:00:00"),
            ("2.28.0.post1", "2022-06-15T00:00:00"),
            ("2.28.0", "2022-06-09T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        assert declared == "2.28.0.post1"
        assert status == Status.OUTDATED  # latest 2.31.0 ≠ ==2.28.0.post1


# ---------------------------------------------------------------------------
# Backport-patch ordering regression
# ---------------------------------------------------------------------------


class TestAnalyzeBackportPatch:
    """Latest version must be determined by version number, not upload date.
    A backport patch (lower version, newer upload date) must NOT be treated
    as the "latest" release.
    """

    def test_should_treat_highest_version_as_latest_when_backport_has_newer_date(
        self,
    ) -> None:
        dep = _make_dep("pkg", "==3.0.0")
        releases = _make_releases(
            # 3.0.0 was released first but is the higher version
            ("3.0.0", "2024-01-01T00:00:00"),
            # 2.31.5 is a backport patch uploaded later
            ("2.31.5", "2024-06-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        # 3.0.0 is up-to-date — the backport patch must not be mistaken for latest
        assert declared == "3.0.0"
        assert status == Status.UP_TO_DATE

    def test_should_be_outdated_relative_to_highest_version_not_newest_upload(
        self,
    ) -> None:
        dep = _make_dep("pkg", "==2.31.5")
        releases = _make_releases(
            ("3.0.0", "2024-01-01T00:00:00"),
            ("2.31.5", "2024-06-01T00:00:00"),
        )

        declared, status = analyze(dep, releases)

        # 3.0.0 is the true latest; being pinned to 2.31.5 is OUTDATED
        assert declared == "2.31.5"
        assert status == Status.OUTDATED

