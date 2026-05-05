import datetime
import enum
from dataclasses import dataclass, field


class Severity(enum.Enum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    NA = "na"


class Status(enum.Enum):
    UP_TO_DATE = "up_to_date"
    OUTDATED = "outdated"
    NOT_AUDITABLE = "not_auditable"
    NO_DATA = "no_data"


@dataclass
class Dependency:
    name: str
    version_spec: str
    source: str
    extras: list[str] = field(default_factory=list)
    is_auditable: bool = True


@dataclass
class PackageRelease:
    version: str
    release_date: datetime.datetime
    yanked: bool


@dataclass
class AuditResult:
    dependency: Dependency
    declared_version: str | None
    installed_version: str | None = None
    latest_version: str | None = None
    installable_version: str | None = None  # max installable given env constraints
    gap_days: int | None = None
    severity: Severity = Severity.NA
    upgrade_type: str | None = None  # semver jump: "major", "minor", "patch", or None
    status: Status = Status.NO_DATA
    latest_release_date: datetime.datetime | None = None
    declared_release_date: datetime.datetime | None = None
    blockers: list[str] = field(default_factory=list)


@dataclass
class AuditReport:
    score: float
    dependencies: list[AuditResult]
    generated_at: datetime.datetime
