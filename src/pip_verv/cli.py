import asyncio
import dataclasses
import datetime
from pathlib import Path

import typer

from pip_verv.analyzer import analyze
from pip_verv.collector import collect, get_latest_stable
from pip_verv.config import load_config, merge_config
from pip_verv.formatter import format_report
from pip_verv.inspector import (
    find_blockers,
    find_installable_version,
    get_installed_packages,
)
from pip_verv.metrics import compute_gap, compute_score
from pip_verv.models import AuditReport, AuditResult, Severity, Status
from pip_verv.parser import parse_sources

app = typer.Typer(name="verv", help="Dependency freshness auditor for Python projects.")


@app.command()
def audit(
    path: Path = typer.Option(Path("."), "--path", help="Project root path"),
    env: list[Path] = typer.Option([], "--env", help="Explicit source files"),
    ignore: list[str] = typer.Option([], "--ignore", help="Packages to ignore"),
    since: str | None = typer.Option(None, "--since", help="Filter: YYYY-MM-DD"),
    fmt: str = typer.Option("rich", "--format", help="Output format: rich|json|csv|md"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Disable cache"),
    score_fail: float | None = typer.Option(
        None, "--score-fail", help="Fail if score < N"
    ),
    gap_fail: int | None = typer.Option(
        None, "--gap-fail", help="Fail if max GAP > N days"
    ),
    max_major: int | None = typer.Option(None, "--max-major", help="Max MAJOR deps"),
    max_outdated: int | None = typer.Option(
        None, "--max-outdated", help="Max outdated deps"
    ),
) -> None:
    # Validate --since
    since_date: datetime.date | None = None
    if since is not None:
        try:
            since_date = datetime.date.fromisoformat(since)
        except ValueError:
            typer.echo(
                f"Invalid --since date format: '{since}'. Expected YYYY-MM-DD.",
                err=True,
            )
            raise typer.Exit(code=2)

    # Load and merge config
    config = load_config(path)
    config = merge_config(
        config,
        score_fail=score_fail,
        gap_fail=gap_fail,
        max_major=max_major,
        max_outdated=max_outdated,
        ignore=ignore if ignore else None,
    )

    # Resolve source files
    sources: list[Path]
    if env:
        sources = list(env)
    else:
        sources = _discover_sources(path)

    if not sources:
        typer.echo("No dependency files found.", err=True)
        return

    # Parse
    dependencies = parse_sources(sources)

    # Filter ignored
    all_ignore = set(config.ignore)
    dependencies = [
        d for d in dependencies if d.name.lower() not in {i.lower() for i in all_ignore}
    ]

    if not dependencies:
        typer.echo("No auditable dependencies found.")
        return

    # Collect PyPI data
    auditable_names = [d.name for d in dependencies if d.is_auditable]
    releases_map = asyncio.run(
        collect(auditable_names, cache_ttl=config.cache_ttl, no_cache=no_cache)
    )

    # Get installed packages
    installed_packages = get_installed_packages()

    # Analyze + compute GAP
    audit_results: list[AuditResult] = []
    for dep in dependencies:
        releases = releases_map.get(dep.name.lower(), []) if dep.is_auditable else []
        latest = get_latest_stable(releases)
        declared_version, status = analyze(dep, releases)

        # Resolve installed version early so compute_gap can use it for the gap baseline
        installed_version = installed_packages.get(dep.name.lower())

        result = AuditResult(
            dependency=dep,
            declared_version=declared_version,
            installed_version=installed_version,
            latest_version=latest.version if latest else None,
            gap_days=None,
            severity=Severity.NA,
            status=status,
            latest_release_date=latest.release_date if latest else None,
            declared_release_date=None,
        )

        # When we know what's installed and it differs from latest, the real
        # situation is OUTDATED regardless of what the spec alone allows.
        if (
            installed_version is not None
            and result.latest_version is not None
            and installed_version != result.latest_version
        ):
            result = dataclasses.replace(result, status=Status.OUTDATED)

        result = compute_gap(result, releases)

        # Compute blockers for any OUTDATED package (covers both spec-blocked
        # and environment-blocked cases).
        blockers: list[str] = []
        installable_version: str | None = None
        if result.status == Status.OUTDATED and result.latest_version is not None:
            blockers = find_blockers(
                dep.name, result.latest_version, installed_packages
            )
            if blockers:
                installable_version = find_installable_version(
                    dep.name, releases, installed_packages
                )
        result = dataclasses.replace(
            result, blockers=blockers, installable_version=installable_version
        )

        audit_results.append(result)

    # Apply --since filter
    if since_date is not None:
        audit_results = [
            r
            for r in audit_results
            if r.latest_release_date is None
            or r.latest_release_date.date() >= since_date
        ]

    # Compute score
    score = compute_score(audit_results)

    # Build report
    report = AuditReport(
        score=score,
        dependencies=audit_results,
        generated_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )

    # Format output
    try:
        output = format_report(report, fmt)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=2)
    if output is not None:
        typer.echo(output)

    # Policy enforcement
    violations: list[str] = []
    if config.score_fail is not None and score < config.score_fail:
        violations.append(f"Health score {score:.1f} < threshold {config.score_fail}")
    if config.gap_fail is not None:
        max_gap = max((r.gap_days or 0 for r in audit_results), default=0)
        if max_gap > config.gap_fail:
            violations.append(f"Max GAP {max_gap} days > threshold {config.gap_fail}")
    if config.max_major is not None:
        major_count = sum(1 for r in audit_results if r.severity == Severity.MAJOR)
        if major_count > config.max_major:
            violations.append(
                f"MAJOR dependencies {major_count} > threshold {config.max_major}"
            )
    if config.max_outdated is not None:
        outdated_count = sum(1 for r in audit_results if r.status == Status.OUTDATED)
        if outdated_count > config.max_outdated:
            violations.append(
                f"Outdated dependencies {outdated_count}"
                f" > threshold {config.max_outdated}"
            )

    if violations:
        for v in violations:
            typer.echo(f"POLICY VIOLATION: {v}", err=True)
        raise typer.Exit(code=1)


def _discover_sources(path: Path) -> list[Path]:
    sources: list[Path] = []
    sources.extend(path.glob("requirements*.txt"))
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        sources.append(pyproject)
    return sorted(sources)
