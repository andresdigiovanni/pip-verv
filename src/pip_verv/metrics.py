import dataclasses

from packaging.version import Version

from pip_verv.models import AuditResult, PackageRelease, Severity

# Days until a package scores 0% for its severity level.
# A MAJOR update 1 year old scores 0%; a PATCH update 4 years old scores 0%.
_GAP_CEILING_BY_SEVERITY: dict[Severity, int] = {
    Severity.MAJOR: 365,
    Severity.MINOR: 730,
    Severity.PATCH: 1460,
}

# Used to find the less severe of two values (NA excluded — it means "no gap").
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.PATCH: 1,
    Severity.MINOR: 2,
    Severity.MAJOR: 3,
}


def _min_severity(a: Severity, b: Severity) -> Severity:
    """Return the less severe of two non-NA severity values."""
    return a if _SEVERITY_RANK.get(a, 0) <= _SEVERITY_RANK.get(b, 0) else b


def _semver_upgrade_type(from_ver_str: str, to_ver_str: str) -> Severity | None:
    """Return the semver magnitude of upgrading from *from_ver_str* to *to_ver_str*.

    Returns None if either version cannot be parsed or they are equal.
    """
    try:
        from_v = Version(from_ver_str)
        to_v = Version(to_ver_str)
    except Exception:
        return None
    if from_v == to_v:
        return None
    if to_v.major != from_v.major:
        return Severity.MAJOR
    if to_v.minor != from_v.minor:
        return Severity.MINOR
    return Severity.PATCH


def _find_release(
    version_str: str, releases: list[PackageRelease]
) -> PackageRelease | None:
    """Find a release by version using packaging.Version equality.

    This handles normalisation differences: "2.28" matches "2.28.0",
    "2.0" matches "2.0.0", etc.  String comparison alone would miss these.
    """
    try:
        target = Version(version_str)
    except Exception:
        return None
    for r in releases:
        try:
            if Version(r.version) == target:
                return r
        except Exception:
            continue
    return None


def compute_gap(result: AuditResult, releases: list[PackageRelease]) -> AuditResult:
    # Prefer installed version for the "from" date; fall back to spec-resolved version.
    effective_version = result.installed_version or result.declared_version
    if effective_version is None or result.latest_version is None:
        return dataclasses.replace(result, severity=Severity.NA, gap_days=None)

    effective_rel = _find_release(effective_version, releases)
    latest_rel = _find_release(result.latest_version, releases)

    if effective_rel is None or latest_rel is None:
        return dataclasses.replace(
            result,
            severity=Severity.NA,
            gap_days=None,
            declared_release_date=effective_rel.release_date if effective_rel else None,
            latest_release_date=latest_rel.release_date if latest_rel else None,
        )

    gap_days = max(0, (latest_rel.release_date - effective_rel.release_date).days)

    # A gap of 0 means installed == latest: no action needed → NA.
    if gap_days == 0:
        return dataclasses.replace(
            result,
            gap_days=0,
            severity=Severity.NA,
            upgrade_type=None,
            declared_release_date=effective_rel.release_date,
            latest_release_date=latest_rel.release_date,
        )

    if gap_days > 365:
        time_severity = Severity.MAJOR
    elif gap_days >= 91:
        time_severity = Severity.MINOR
    else:
        time_severity = Severity.PATCH

    # Cap time-based severity by the semver magnitude of the actual version jump.
    # A patch-level upgrade cannot be MAJOR-severity no matter how old it is.
    semver_type = _semver_upgrade_type(effective_version, result.latest_version)
    upgrade_type_str = semver_type.value if semver_type else None
    severity = (
        _min_severity(time_severity, semver_type)
        if semver_type is not None
        else time_severity
    )

    return dataclasses.replace(
        result,
        gap_days=gap_days,
        severity=severity,
        upgrade_type=upgrade_type_str,
        declared_release_date=effective_rel.release_date,
        latest_release_date=latest_rel.release_date,
    )


def _package_score(result: AuditResult) -> float | None:
    """Return a 0-100 freshness score for a single package.

    Returns 100 for packages confirmed up-to-date (gap_days == 0).
    Returns None for packages with unknown staleness (gap_days is None
    or severity is NA with no gap data) — these are excluded from the average.
    Returns a linear score for outdated packages, reaching 0 when gap_days
    meets the severity-specific ceiling.
    """
    if result.gap_days == 0:
        return 100.0
    if result.severity == Severity.NA or result.gap_days is None:
        return None  # unknown freshness — exclude from average
    ceiling = _GAP_CEILING_BY_SEVERITY.get(result.severity, 1460)
    return max(0.0, 100.0 * (1.0 - result.gap_days / ceiling))


def compute_score(results: list[AuditResult]) -> float:
    """Compute a 0-100 health score as the mean per-package score.

    Packages with confirmed gap_days == 0 contribute 100% (up-to-date).
    Packages with unknown freshness (no PyPI data, range constraint unknowns)
    are excluded from the average.
    Outdated packages are scored linearly: MAJOR reaches 0% at 1 year,
    MINOR at 2 years, PATCH at 4 years.
    """
    scores = [_package_score(r) for r in results]
    known = [s for s in scores if s is not None]
    if not known:
        return 100.0
    return sum(known) / len(known)
