import csv
import io
import json

from rich.console import Console
from rich.table import Table

from pip_verv.models import AuditReport, AuditResult, Severity, Status

_SEVERITY_ORDER = [Severity.MAJOR, Severity.MINOR, Severity.PATCH, Severity.NA]
_SEVERITY_COLORS = {
    Severity.MAJOR: "red",
    Severity.MINOR: "yellow",
    Severity.PATCH: "green",
    Severity.NA: "dim",
}


def format_report(report: AuditReport, fmt: str) -> str | None:
    match fmt:
        case "json":
            return _format_json(report)
        case "csv":
            return _format_csv(report)
        case "md":
            return _format_md(report)
        case "rich":
            _format_rich(report)
            return None
        case _:
            raise ValueError(f"Unknown format: {fmt!r}")


def _compute_target(r: AuditResult) -> str | None:
    """Version the user should upgrade to right now.

    - Not outdated → null (nothing to do)
    - Outdated, no blockers → latest (upgrade freely)
    - Outdated, blocked, can partially upgrade → highest version within env constraints
    - Outdated, already at env ceiling (installable == installed) → null
    """
    if r.status != Status.OUTDATED:
        return None
    if not r.blockers:
        return r.latest_version
    if r.installable_version and r.installable_version != r.installed_version:
        return r.installable_version
    return None


def _result_to_dict(r: AuditResult) -> dict[str, object]:
    return {
        "name": r.dependency.name,
        "status": r.status.value,
        "installed": r.installed_version,
        "latest": r.latest_version,
        "target": _compute_target(r),
        "bump": r.upgrade_type,
        "urgency": r.severity.value,
        "days_behind": r.gap_days,
        "blockers": r.blockers,
    }


def _format_json(report: AuditReport) -> str:
    data = {
        "score": report.score,
        "generated_at": report.generated_at.isoformat(),
        "dependencies": [_result_to_dict(r) for r in report.dependencies],
    }
    return json.dumps(data, indent=2)


def _format_csv(report: AuditReport) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "name",
            "status",
            "installed",
            "latest",
            "target",
            "bump",
            "urgency",
            "days_behind",
            "blockers",
        ]
    )
    for r in report.dependencies:
        writer.writerow(
            [
                r.dependency.name,
                r.status.value,
                r.installed_version or "",
                r.latest_version or "",
                _compute_target(r) or "",
                r.upgrade_type or "",
                r.severity.value,
                r.gap_days if r.gap_days is not None else "",
                ",".join(r.blockers),
            ]
        )
    return buf.getvalue()


def _format_md(report: AuditReport) -> str:
    lines = [
        "| Name | Status | Installed | Latest | Target | Bump | Urgency | Days Behind"
        " | Blockers |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in report.dependencies:
        blockers_str = ", ".join(r.blockers)
        lines.append(
            f"| {r.dependency.name} "
            f"| {r.status.value} "
            f"| {r.installed_version or ''} "
            f"| {r.latest_version or ''} "
            f"| {_compute_target(r) or ''} "
            f"| {r.upgrade_type or ''} "
            f"| {r.severity.value} "
            f"| {r.gap_days if r.gap_days is not None else ''} "
            f"| {blockers_str} |"
        )
    lines.append(f"\n**Health Score: {report.score:.1f}**")
    return "\n".join(lines)


def _format_rich(report: AuditReport) -> None:
    console = Console()
    table = Table(title="Dependency Audit Report")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Installed")
    table.add_column("Latest")
    table.add_column("Target")
    table.add_column("Bump")
    table.add_column("Urgency")
    table.add_column("Days Behind")
    table.add_column("Blockers")

    sorted_results = sorted(
        report.dependencies,
        key=lambda r: _SEVERITY_ORDER.index(r.severity),
    )

    for r in sorted_results:
        color = _SEVERITY_COLORS.get(r.severity, "")
        table.add_row(
            f"[{color}]{r.dependency.name}[/{color}]",
            r.status.value,
            r.installed_version or "",
            r.latest_version or "",
            _compute_target(r) or "",
            r.upgrade_type or "",
            f"[{color}]{r.severity.value}[/{color}]",
            str(r.gap_days) if r.gap_days is not None else "",
            ", ".join(r.blockers),
        )

    console.print(table)

    score = report.score
    if score >= 90:
        score_color = "green"
    elif score >= 70:
        score_color = "yellow"
    else:
        score_color = "red"

    console.print(f"[{score_color}]Health Score: {score:.1f}[/{score_color}]")
