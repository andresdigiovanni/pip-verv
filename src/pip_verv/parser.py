import tomllib
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement

from pip_verv.models import Dependency

_URL_PREFIXES = ("http://", "https://", "git+")


def parse_sources(paths: list[Path]) -> list[Dependency]:
    deps: list[Dependency] = []
    seen_names: set[str] = set()
    for path in paths:
        if path.suffix == ".toml":
            new_deps = _parse_pyproject(path)
        else:
            new_deps = _parse_requirements(path, seen=set())
        for dep in new_deps:
            key = dep.name.lower()
            if key not in seen_names:
                seen_names.add(key)
                deps.append(dep)
    return deps


def _parse_requirements(path: Path, seen: set[Path]) -> list[Dependency]:
    resolved = path.resolve()
    if resolved in seen:
        return []
    seen.add(resolved)

    deps: list[Dependency] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    for raw_line in lines:
        line = raw_line.strip()
        # Strip inline comments
        comment_pos = line.find("#")
        if comment_pos != -1:
            line = line[:comment_pos].strip()
        if not line:
            continue
        # Skip constraint files and editable installs
        if line.startswith("-c ") or line.startswith("-e ") or line == "-e":
            continue
        # Recursive include with path traversal protection
        if line.startswith("-r "):
            include_path = (path.parent / line[3:].strip()).resolve()
            base_dir = path.parent.resolve()
            if not str(include_path).startswith(str(base_dir)):
                continue
            deps.extend(_parse_requirements(include_path, seen=seen))
            continue
        # URL / VCS deps — not auditable
        if any(line.startswith(prefix) for prefix in _URL_PREFIXES):
            name = line.split("/")[-1].split("@")[0] or line
            deps.append(
                Dependency(
                    name=name,
                    version_spec="",
                    source=str(path),
                    is_auditable=False,
                )
            )
            continue
        # Parse with packaging
        dep = _parse_requirement_line(line, source=str(path))
        if dep is not None:
            deps.append(dep)

    return deps


def _parse_requirement_line(line: str, source: str) -> Dependency | None:
    try:
        req = Requirement(line)
    except InvalidRequirement:
        return Dependency(name=line, version_spec="", source=source, is_auditable=False)

    if req.url:
        return Dependency(
            name=req.name,
            version_spec="",
            source=source,
            extras=sorted(req.extras),
            is_auditable=False,
        )

    return Dependency(
        name=req.name,
        version_spec=str(req.specifier),
        source=source,
        extras=sorted(req.extras),
        is_auditable=True,
    )


def _parse_pyproject(path: Path) -> list[Dependency]:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return []

    deps: list[Dependency] = []
    project = data.get("project", {})

    # [project.dependencies] — PEP 621
    for dep_str in project.get("dependencies", []):
        dep = _parse_pep508(dep_str, source=str(path))
        if dep is not None:
            deps.append(dep)

    # [project.optional-dependencies] — PEP 621
    optional = project.get("optional-dependencies", {})
    for _group, group_deps in optional.items():
        for dep_str in group_deps:
            dep = _parse_pep508(dep_str, source=str(path))
            if dep is not None:
                deps.append(dep)

    # [dependency-groups] — PEP 735 (used by uv and others)
    dep_groups = data.get("dependency-groups", {})
    for _group, group_deps in dep_groups.items():
        if not isinstance(group_deps, list):
            continue
        for item in group_deps:
            if isinstance(item, str):
                dep = _parse_pep508(item, source=str(path))
                if dep is not None:
                    deps.append(dep)
            # dicts like {include-group = "dev"} are intentionally skipped

    # [tool.poetry.dependencies] and [tool.poetry.group.*.dependencies]
    poetry = data.get("tool", {}).get("poetry", {})
    if poetry:
        for name, constraint in poetry.get("dependencies", {}).items():
            if name.lower() == "python":
                continue
            dep = _parse_poetry_dep(name, constraint, source=str(path))
            if dep is not None:
                deps.append(dep)

        for _group_name, group_data in poetry.get("group", {}).items():
            if not isinstance(group_data, dict):
                continue
            for name, constraint in group_data.get("dependencies", {}).items():
                dep = _parse_poetry_dep(name, constraint, source=str(path))
                if dep is not None:
                    deps.append(dep)

    return deps


def _parse_poetry_dep(name: str, constraint: object, source: str) -> Dependency | None:
    """Parse a Poetry-format dependency value (string or inline table)."""
    extras: list[str] = []

    if isinstance(constraint, str):
        version_str = constraint
    elif isinstance(constraint, dict):
        if any(k in constraint for k in ("git", "path", "url")):
            return Dependency(name=name, version_spec="", source=source, is_auditable=False)
        version_str = constraint.get("version", "*")  # type: ignore[arg-type]
        raw_extras = constraint.get("extras", [])
        if isinstance(raw_extras, list):
            extras = sorted(str(e) for e in raw_extras)
    else:
        return None

    if not isinstance(version_str, str):
        return None

    if version_str == "*":
        version_spec = ""
    elif version_str.startswith("^"):
        try:
            version_spec = _caret_to_pep440(version_str[1:])
        except (ValueError, IndexError):
            version_spec = ""
    elif version_str.startswith("~"):
        try:
            version_spec = _tilde_to_pep440(version_str[1:])
        except (ValueError, IndexError):
            version_spec = ""
    else:
        version_spec = version_str

    return Dependency(
        name=name,
        version_spec=version_spec,
        source=source,
        extras=extras,
        is_auditable=True,
    )


def _caret_to_pep440(version: str) -> str:
    """Convert Poetry's ^X.Y.Z caret constraint to a PEP 440 specifier set.

    ^1.2.3  →  >=1.2.3,<2.0.0
    ^0.2.3  →  >=0.2.3,<0.3.0
    ^0.0.3  →  >=0.0.3,<0.0.4
    """
    parts = version.split(".")
    nums = [int(p) for p in parts]
    upper = list(nums)
    for i, n in enumerate(nums):
        if n != 0:
            upper[i] = n + 1
            for j in range(i + 1, len(upper)):
                upper[j] = 0
            break
    else:
        upper[-1] += 1
    return f">={version},<{'.'.join(str(n) for n in upper)}"


def _tilde_to_pep440(version: str) -> str:
    """Convert Poetry's ~X.Y.Z tilde constraint to a PEP 440 specifier set.

    ~1.2.3  →  >=1.2.3,<1.3.0
    ~1.2    →  >=1.2,<1.3
    ~1      →  >=1,<2
    """
    parts = version.split(".")
    nums = [int(p) for p in parts]
    if len(nums) == 1:
        upper = [nums[0] + 1]
    else:
        upper = list(nums)
        upper[1] += 1
        for j in range(2, len(upper)):
            upper[j] = 0
    return f">={version},<{'.'.join(str(n) for n in upper)}"


def _parse_pep508(dep_str: str, source: str) -> Dependency | None:
    try:
        req = Requirement(dep_str)
    except InvalidRequirement:
        return Dependency(
            name=dep_str, version_spec="", source=source, is_auditable=False
        )

    if req.url:
        return Dependency(
            name=req.name,
            version_spec="",
            source=source,
            extras=sorted(req.extras),
            is_auditable=False,
        )

    return Dependency(
        name=req.name,
        version_spec=str(req.specifier),
        source=source,
        extras=sorted(req.extras),
        is_auditable=True,
    )
