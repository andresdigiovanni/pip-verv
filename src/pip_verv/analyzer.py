from packaging.specifiers import SpecifierSet
from packaging.version import Version

from pip_verv.models import Dependency, PackageRelease, Status


def analyze(
    dep: Dependency, releases: list[PackageRelease]
) -> tuple[str | None, Status]:
    if not dep.is_auditable:
        return None, Status.NOT_AUDITABLE
    if not releases:
        return None, Status.NO_DATA

    # Select latest stable by version number (highest semver), not by upload date.
    # Sorting by date would incorrectly pick a backport patch (lower version,
    # newer upload) over a more recent major/minor release.
    latest = max(releases, key=lambda r: Version(r.version))
    spec = SpecifierSet(dep.version_spec, prereleases=False)

    # Current: latest release from PyPI that satisfies the declared constraint,
    # mirroring what a resolver (pip/uv) would install.
    matching = [r for r in releases if Version(r.version) in spec]
    current_version: str | None = (
        max(matching, key=lambda r: r.release_date).version if matching else None
    )

    # Status: does the latest stable version satisfy the declared constraint?
    if Version(latest.version) in spec:
        status = Status.UP_TO_DATE
    else:
        status = Status.OUTDATED

    return current_version, status
