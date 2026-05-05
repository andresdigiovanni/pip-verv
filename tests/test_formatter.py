import datetime
import json

import pytest

from pip_verv.formatter import format_report
from pip_verv.models import (
    AuditReport,
    AuditResult,
    Dependency,
    Severity,
    Status,
)


def _make_dep(name: str = "requests") -> Dependency:
    return Dependency(name=name, version_spec=">=2.0", source="req.txt")


def _make_result(
    name: str = "requests",
    declared: str | None = "2.28.0",
    latest: str | None = "2.31.0",
    gap_days: int | None = 210,
    severity: Severity = Severity.MINOR,
    status: Status = Status.OUTDATED,
    installed: str | None = None,
    installable: str | None = None,
    upgrade_type: str | None = "minor",
    blockers: list[str] | None = None,
) -> AuditResult:
    return AuditResult(
        dependency=_make_dep(name),
        declared_version=declared,
        installed_version=installed,
        installable_version=installable,
        latest_version=latest,
        gap_days=gap_days,
        severity=severity,
        upgrade_type=upgrade_type,
        status=status,
        latest_release_date=datetime.datetime(2023, 5, 22),
        declared_release_date=datetime.datetime(2022, 6, 9),
        blockers=blockers if blockers is not None else [],
    )


def _make_report(
    results: list[AuditResult] | None = None,
    score: float = 82.0,
) -> AuditReport:
    return AuditReport(
        score=score,
        dependencies=results if results is not None else [_make_result()],
        generated_at=datetime.datetime(2026, 5, 4, 0, 0, 0),
    )


class TestFormatJson:
    def test_should_return_valid_json(self) -> None:
        report = _make_report()

        output = format_report(report, "json")

        assert output is not None
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_should_include_score_and_generated_at(self) -> None:
        report = _make_report(score=82.0)

        output = format_report(report, "json")

        assert output is not None
        parsed = json.loads(output)
        assert parsed["score"] == 82.0
        assert "generated_at" in parsed

    def test_should_serialize_generated_at_as_iso8601(self) -> None:
        report = _make_report()

        output = format_report(report, "json")

        assert output is not None
        parsed = json.loads(output)
        # Should be parseable as ISO 8601
        datetime.datetime.fromisoformat(parsed["generated_at"])

    def test_should_return_valid_json_for_empty_dependencies(self) -> None:
        report = _make_report(results=[])

        output = format_report(report, "json")

        assert output is not None
        parsed = json.loads(output)
        assert parsed["dependencies"] == []

    def test_should_serialize_gap_days_none_as_null(self) -> None:
        result = _make_result(gap_days=None)
        report = _make_report(results=[result])

        output = format_report(report, "json")

        assert output is not None
        parsed = json.loads(output)
        assert parsed["dependencies"][0]["days_behind"] is None

    def test_should_include_correct_dependency_fields(self) -> None:
        report = _make_report()

        output = format_report(report, "json")

        assert output is not None
        parsed = json.loads(output)
        dep = parsed["dependencies"][0]
        assert dep["name"] == "requests"
        assert "current" not in dep
        assert "installable" not in dep
        assert "upgrade_type" not in dep
        assert "gap_days" not in dep
        assert "severity" not in dep
        assert dep["status"] == "outdated"
        assert dep["installed"] is None
        assert dep["latest"] == "2.31.0"
        # No blockers + outdated → target = latest
        assert dep["target"] == "2.31.0"
        assert dep["bump"] == "minor"
        assert dep["urgency"] == "minor"
        assert dep["days_behind"] == 210
        assert dep["blockers"] == []

    def test_should_serialize_installed_version_and_blockers(self) -> None:
        # blocked + installable(2.31.0) > installed(2.30.0) → target = 2.31.0
        result = _make_result(
            installed="2.30.0",
            installable="2.31.0",
            blockers=["pkg-a (<3.0)"],
        )
        report = _make_report(results=[result])

        output = format_report(report, "json")

        assert output is not None
        parsed = json.loads(output)
        dep = parsed["dependencies"][0]
        assert dep["installed"] == "2.30.0"
        assert dep["target"] == "2.31.0"
        assert dep["blockers"] == ["pkg-a (<3.0)"]

    def test_should_set_target_null_when_blocked_at_ceiling(self) -> None:
        # blocked + installable == installed → already at env ceiling → target null
        result = _make_result(
            installed="2.30.0",
            installable="2.30.0",
            blockers=["pkg-a (<2.31)"],
        )
        report = _make_report(results=[result])

        output = format_report(report, "json")

        assert output is not None
        dep = json.loads(output)["dependencies"][0]
        assert dep["target"] is None


class TestFormatCsv:
    def test_should_return_csv_with_correct_header(self) -> None:
        report = _make_report()

        output = format_report(report, "csv")

        assert output is not None
        first_line = output.splitlines()[0]
        assert "name" in first_line
        assert "status" in first_line
        assert "installed" in first_line
        assert "latest" in first_line
        assert "target" in first_line
        assert "bump" in first_line
        assert "urgency" in first_line
        assert "days_behind" in first_line
        assert "blockers" in first_line
        # Old field names must not appear
        assert "current" not in first_line
        assert "installable" not in first_line
        assert "upgrade_type" not in first_line
        assert "gap_days" not in first_line
        assert "severity" not in first_line

    def test_should_return_valid_csv_for_empty_dependencies(self) -> None:
        report = _make_report(results=[])

        output = format_report(report, "csv")

        assert output is not None
        lines = [line for line in output.splitlines() if line]
        assert len(lines) == 1  # Only header

    def test_should_use_empty_string_for_none_gap_days(self) -> None:
        result = _make_result(gap_days=None)
        report = _make_report(results=[result])

        output = format_report(report, "csv")

        assert output is not None
        data_line = output.splitlines()[1]
        # days_behind should be empty for None gap
        parts = data_line.split(",")
        gap_idx = output.splitlines()[0].split(",").index("days_behind")
        assert parts[gap_idx] == ""


class TestFormatMd:
    def test_should_return_markdown_table_syntax(self) -> None:
        report = _make_report()

        output = format_report(report, "md")

        assert output is not None
        assert output.startswith("|")

    def test_should_return_valid_markdown_for_empty_dependencies(self) -> None:
        report = _make_report(results=[])

        output = format_report(report, "md")

        assert output is not None
        assert "|" in output

    def test_should_use_empty_string_for_none_gap_days(self) -> None:
        result = _make_result(gap_days=None)
        report = _make_report(results=[result])

        output = format_report(report, "md")

        assert output is not None
        # None gap_days should not appear as "None" in the output
        assert "None" not in output


class TestFormatRich:
    def test_should_return_none(self) -> None:
        report = _make_report()

        result = format_report(report, "rich")

        assert result is None

    def test_should_not_raise_for_empty_dependencies(self) -> None:
        report = _make_report(results=[])

        # Should not raise
        format_report(report, "rich")


class TestFormatUnknown:
    def test_should_raise_value_error_for_unknown_format(self) -> None:
        report = _make_report()

        with pytest.raises(ValueError, match="Unknown format"):
            format_report(report, "xml")
