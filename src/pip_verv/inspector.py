"""Environment inspector: discovers installed packages and dependency constraints."""

from importlib.metadata import PackageNotFoundError, distributions, requires

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from pip_verv.models import PackageRelease


class InspectorError(Exception):
    """Raised when environment inspection fails."""


def get_installed_packages() -> dict[str, str]:
    """Return mapping of installed package names to their versions.

    Uses importlib.metadata (Python 3.11+ stdlib) to inspect the current
    environment. Package names are normalized to lowercase.

    Returns an empty dict if inspection fails or no packages are found.
    """
    packages: dict[str, str] = {}
    try:
        for dist in distributions():
            name = dist.metadata["Name"] if "Name" in dist.metadata else None
            version = (
                dist.metadata["Version"] if "Version" in dist.metadata else dist.version
            )
            if name and version:
                packages[name.lower()] = version
    except Exception:
        return {}
    return packages


def get_package_requirements(package_name: str) -> list[str]:
    """Return the declared requirements for an installed package.

    Args:
        package_name: Name of installed package (case-insensitive).

    Returns:
        List of requirement specifier strings. Empty list if the package is
        not installed, has no requirements, or its metadata cannot be read.
        Extras-conditional requirements (containing ';') are excluded.
    """
    try:
        reqs = requires(package_name.lower())
    except PackageNotFoundError:
        return []
    if reqs is None:
        return []
    return [r.strip() for r in reqs if ";" not in r]


def find_blockers(
    package_name: str,
    latest_version: str,
    installed_packages: dict[str, str],
) -> list[str]:
    """Find packages preventing upgrade of *package_name* to *latest_version*.

    For each installed package, inspect its declared requirements. If any
    requirement targets *package_name* with a specifier that excludes
    *latest_version*, that package is considered a blocker.

    Args:
        package_name: The package whose upgrade path is being analysed.
        latest_version: The latest available version (from PyPI).
        installed_packages: Mapping of {package_name: version} for all installed
            packages (as returned by :func:`get_installed_packages`).

    Returns:
        Sorted list of package names whose constraints block the upgrade.
        Returns an empty list when no blockers are found or the latest version
        string cannot be parsed.
    """
    try:
        latest_ver = Version(latest_version)
    except InvalidVersion:
        return []

    target_name = package_name.lower()
    blockers: list[str] = []

    for pkg_name in installed_packages:
        for req_str in get_package_requirements(pkg_name):
            try:
                req = Requirement(req_str)
            except Exception:
                continue
            if req.name.lower() == target_name and latest_ver not in req.specifier:
                spec_str = str(req.specifier)
                label = f"{pkg_name} ({spec_str})" if spec_str else pkg_name
                blockers.append(label)
                break  # one blocker entry per package is enough

    return sorted(blockers)


def find_installable_version(
    package_name: str,
    releases: list[PackageRelease],
    installed_packages: dict[str, str],
) -> str | None:
    """Return the highest version of *package_name* installable given env constraints.

    Collects all specifiers that installed packages declare for *package_name*,
    combines them, and returns the latest PyPI release that satisfies every
    constraint.  Returns None if no release satisfies the combined constraints
    or if no constraints are found (caller should use *latest_version* instead).

    Args:
        package_name: The package to find the installable version for.
        releases: All known PyPI releases for that package (from the collector).
        installed_packages: Mapping of {name: version} for all installed packages.
    """
    combined = SpecifierSet()
    target_name = package_name.lower()
    has_constraints = False

    for pkg_name in installed_packages:
        for req_str in get_package_requirements(pkg_name):
            try:
                req = Requirement(req_str)
            except Exception:
                continue
            if req.name.lower() == target_name and req.specifier:
                combined &= req.specifier
                has_constraints = True

    if not has_constraints:
        return None  # no env constraints → latest is installable

    satisfying: list[PackageRelease] = []
    for r in releases:
        try:
            if Version(r.version) in combined:
                satisfying.append(r)
        except Exception:
            continue

    if not satisfying:
        return None

    return max(satisfying, key=lambda r: Version(r.version)).version
