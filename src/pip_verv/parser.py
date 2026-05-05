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

    # [project.dependencies]
    for dep_str in project.get("dependencies", []):
        dep = _parse_pep508(dep_str, source=str(path))
        if dep is not None:
            deps.append(dep)

    # [project.optional-dependencies]
    optional = project.get("optional-dependencies", {})
    for _group, group_deps in optional.items():
        for dep_str in group_deps:
            dep = _parse_pep508(dep_str, source=str(path))
            if dep is not None:
                deps.append(dep)

    return deps


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
