import datetime

import pytest

from pip_verv.models import (
    AuditReport,
    AuditResult,
    Dependency,
    PackageRelease,
    Severity,
    Status,
)


class TestSeverityEnum:
    def test_should_have_major_value(self) -> None:
        assert Severity.MAJOR.value == "major"

    def test_should_have_minor_value(self) -> None:
        assert Severity.MINOR.value == "minor"

    def test_should_have_patch_value(self) -> None:
        assert Severity.PATCH.value == "patch"

    def test_should_have_na_value(self) -> None:
        assert Severity.NA.value == "na"


class TestStatusEnum:
    def test_should_have_up_to_date_value(self) -> None:
        assert Status.UP_TO_DATE.value == "up_to_date"

    def test_should_have_outdated_value(self) -> None:
        assert Status.OUTDATED.value == "outdated"

    def test_should_have_not_auditable_value(self) -> None:
        assert Status.NOT_AUDITABLE.value == "not_auditable"

    def test_should_have_no_data_value(self) -> None:
        assert Status.NO_DATA.value == "no_data"


class TestDependency:
    def test_should_instantiate_with_required_fields(self) -> None:
        dep = Dependency(
            name="requests", version_spec=">=2.0", source="requirements.txt"
        )

        assert dep.name == "requests"
        assert dep.version_spec == ">=2.0"
        assert dep.source == "requirements.txt"

    def test_should_default_is_auditable_to_true(self) -> None:
        dep = Dependency(name="requests", version_spec=">=2.0", source="req.txt")

        assert dep.is_auditable is True

    def test_should_default_extras_to_empty_list(self) -> None:
        dep = Dependency(name="requests", version_spec=">=2.0", source="req.txt")

        assert dep.extras == []

    def test_should_accept_extras(self) -> None:
        dep = Dependency(
            name="requests",
            version_spec=">=2.0",
            source="req.txt",
            extras=["security", "socks"],
        )

        assert dep.extras == ["security", "socks"]

    def test_should_accept_is_auditable_false(self) -> None:
        dep = Dependency(
            name="mylib", version_spec="", source="req.txt", is_auditable=False
        )

        assert dep.is_auditable is False


class TestPackageRelease:
    def test_should_instantiate_correctly(self) -> None:
        dt = datetime.datetime(2023, 1, 15, 12, 0, 0)

        release = PackageRelease(version="2.28.0", release_date=dt, yanked=False)

        assert release.version == "2.28.0"
        assert release.release_date == dt
        assert release.yanked is False

    def test_should_accept_yanked_true(self) -> None:
        dt = datetime.datetime(2023, 1, 1)

        release = PackageRelease(version="1.0.0", release_date=dt, yanked=True)

        assert release.yanked is True


class TestAuditResult:
    def test_should_instantiate_with_all_none_nullable_fields(self) -> None:
        dep = Dependency(name="pkg", version_spec=">=1.0", source="req.txt")

        result = AuditResult(
            dependency=dep,
            declared_version=None,
            latest_version=None,
            gap_days=None,
            severity=Severity.NA,
            status=Status.NO_DATA,
            latest_release_date=None,
            declared_release_date=None,
        )

        assert result.declared_version is None
        assert result.latest_version is None
        assert result.gap_days is None
        assert result.latest_release_date is None
        assert result.declared_release_date is None

    def test_should_instantiate_with_all_fields_populated(self) -> None:
        dep = Dependency(name="requests", version_spec="==2.28.0", source="req.txt")
        now = datetime.datetime(2024, 1, 1)

        result = AuditResult(
            dependency=dep,
            declared_version="2.28.0",
            latest_version="2.31.0",
            gap_days=210,
            severity=Severity.MINOR,
            status=Status.OUTDATED,
            latest_release_date=now,
            declared_release_date=now,
        )

        assert result.declared_version == "2.28.0"
        assert result.latest_version == "2.31.0"
        assert result.gap_days == 210
        assert result.severity == Severity.MINOR
        assert result.status == Status.OUTDATED

    def test_should_default_installed_version_to_none(self) -> None:
        dep = Dependency(name="pkg", version_spec=">=1.0", source="req.txt")

        result = AuditResult(
            dependency=dep,
            declared_version=None,
        )

        assert result.installed_version is None

    def test_should_default_installable_version_to_none(self) -> None:
        dep = Dependency(name="pkg", version_spec=">=1.0", source="req.txt")

        result = AuditResult(dependency=dep, declared_version=None)

        assert result.installable_version is None

    def test_should_default_upgrade_type_to_none(self) -> None:
        dep = Dependency(name="pkg", version_spec=">=1.0", source="req.txt")

        result = AuditResult(dependency=dep, declared_version=None)

        assert result.upgrade_type is None

    def test_should_default_blockers_to_empty_list(self) -> None:
        dep = Dependency(name="pkg", version_spec=">=1.0", source="req.txt")

        result = AuditResult(
            dependency=dep,
            declared_version=None,
        )

        assert result.blockers == []

    def test_should_accept_installed_version_and_blockers(self) -> None:
        dep = Dependency(name="requests", version_spec=">=2.0", source="req.txt")

        result = AuditResult(
            dependency=dep,
            declared_version="2.28.0",
            installed_version="2.30.0",
            installable_version="2.31.0",
            upgrade_type="minor",
            blockers=["pkg-a (<3.0,>=2.0)"],
        )

        assert result.installed_version == "2.30.0"
        assert result.installable_version == "2.31.0"
        assert result.upgrade_type == "minor"
        assert result.blockers == ["pkg-a (<3.0,>=2.0)"]


class TestAuditReport:
    def test_should_instantiate_correctly(self) -> None:
        now = datetime.datetime(2026, 5, 4)

        report = AuditReport(score=82.0, dependencies=[], generated_at=now)

        assert report.score == 82.0
        assert report.dependencies == []
        assert report.generated_at == now

    @pytest.mark.parametrize("score", [0.0, 100.0, 50.5])
    def test_should_accept_valid_score_values(self, score: float) -> None:
        report = AuditReport(
            score=score, dependencies=[], generated_at=datetime.datetime.now()
        )

        assert report.score == score
