![PyPI version](https://img.shields.io/pypi/v/pip-verv)
[![PyPI Downloads](https://static.pepy.tech/badge/pip-verv)](https://pepy.tech/projects/pip-verv)

```text
██████╗ ██╗██████╗       ██╗   ██╗███████╗██████╗ ██╗   ██╗
██╔══██╗██║██╔══██╗      ██║   ██║██╔════╝██╔══██╗██║   ██║
██████╔╝██║██████╔╝█████╗██║   ██║█████╗  ██████╔╝██║   ██║
██╔═══╝ ██║██╔═══╝ ╚════╝╚██╗ ██╔╝██╔══╝  ██╔══██╗╚██╗ ██╔╝
██║     ██║██║             ╚████╔╝ ███████╗██║  ██║ ╚████╔╝
╚═╝     ╚═╝╚═╝              ╚═══╝  ╚══════╝╚═╝  ╚═╝  ╚═══╝
```

**pip-verv** (Version Review) is a read-only CLI tool that audits the temporal freshness of Python dependencies. It measures how long each dependency has been behind the latest stable release on PyPI, calculates a per-package GAP in days, and produces a project-wide Health Score (0–100). It does not install, modify, or resolve environments.

---

## Installation

```bash
pip install pip-verv
```

---

## Usage

```bash
# Audit the current directory
verv --path .

# Output as JSON
verv --format json

# CI: fail if Health Score drops below 70
verv --score-fail 70

# CI: fail if any dependency GAP exceeds 365 days, with max 2 MAJOR-outdated deps
verv --score-fail 70 --gap-fail 365 --max-major 2

# Export to file
verv --format json > audit.json

# Audit only dependencies with a release newer than a date
verv --since 2025-01-01

# Audit explicit files
verv --env requirements.txt --env requirements-dev.txt

# Skip cache
verv --no-cache
```

---

## CLI Flags

| Flag               | Description                                              |
|--------------------|----------------------------------------------------------|
| `--path PATH`      | Project root to scan (default: `.`)                      |
| `--env FILE`       | Explicit source file(s); repeatable; disables auto-discovery |
| `--ignore PKG`     | Package name(s) to exclude; repeatable                   |
| `--since DATE`     | Include only deps whose latest stable release is after `YYYY-MM-DD` |
| `--format FORMAT`  | Output format: `rich` (default), `json`, `csv`, `md`     |
| `--no-cache`       | Disable the file-based PyPI response cache               |
| `--score-fail N`   | Exit non-zero if Health Score < N                        |
| `--gap-fail N`     | Exit non-zero if any dependency GAP > N days             |
| `--max-major N`    | Exit non-zero if MAJOR-outdated dependency count > N     |
| `--max-outdated N` | Exit non-zero if total outdated dependency count > N     |

---

## Output Fields (All Formats)

Each dependency row/object includes:

| Field         | Meaning                                                                                 |
|-------------- |----------------------------------------------------------------------------------------|
| `name`        | Package name                                                                           |
| `status`      | `up_to_date`, `outdated`, or `no_data`                                                 |
| `installed`   | Version currently installed in the environment (if present)                            |
| `latest`      | Latest stable version available on PyPI                                                |
| `target`      | Version you should upgrade to now (see below); `null` if up-to-date or blocked         |
| `bump`        | Semver jump required to reach `target` (`major`, `minor`, `patch`, or `null`)          |
| `urgency`     | How pressing the upgrade is (hybrid of time and semver: `major`, `minor`, `patch`, `na`)|
| `days_behind` | Days between your version's release and the latest release                             |
| `blockers`    | List of packages whose constraints prevent upgrading to the latest version              |

### `target` field explained
- **Up-to-date**: `null` (nothing to do)
- **Outdated, no blockers**: `latest` (upgrade freely)
- **Outdated, blocked, can partially upgrade**: highest version allowed by environment constraints
- **Outdated, blocked at current version**: `null` (already at env ceiling; see `blockers`)

---

## Output Formats

| Format | Description |
|--------|-------------|
| `rich` | Colour-coded terminal table grouped by urgency, with Health Score summary |
| `json` | Machine-readable JSON with score and per-dependency detail |
| `csv`  | Comma-separated values, one row per dependency |
| `md`   | Markdown table, suitable for reports or PR comments |

All formats include the fields above, in this order:

`name, status, installed, latest, target, bump, urgency, days_behind, blockers`

---

## Health Score

The Health Score (0–100) is the mean of per-package freshness scores:

- **Up-to-date**: 100%
- **Outdated**: Linear penalty by urgency:
    - `major`: 0% at 365 days behind
    - `minor`: 0% at 730 days
    - `patch`: 0% at 1460 days
- **Unknown freshness**: Excluded from average

**Formula:**

$$
\text{score} = \frac{\sum \text{per-package scores}}{\text{count of known-freshness packages}}
$$

| Score  | Status               |
|--------|----------------------|
| 90–100 | Excellent            |
| 70–89  | Healthy              |
| 50–69  | Needs attention      |
| < 50   | High risk            |

---

## Example Output

```text
| Name              | Status     | Installed | Latest | Target | Bump  | Urgency | Days Behind | Blockers               |
|-------------------|------------|-----------|--------|--------|-------|---------|-------------|------------------------|
| hydra-core        | up_to_date | 1.3.2     | 1.3.2  |        |       | na      | 0           |                        |
| pandas            | outdated   | 2.3.3     | 3.0.3  |        | major | minor   | 223         | streamlit (<3,>=1.4.0) |
| omegaconf         | up_to_date | 2.3.0     | 2.3.0  |        |       | na      | 0           |                        |
| tqdm              | outdated   | 4.67.1    | 4.67.3 | 4.67.3 | patch | patch   | 435         |                        |
| pyarrow           | outdated   | 23.0.0    | 24.0.0 | 24.0.0 | major | minor   | 92          |                        |
| pydantic          | outdated   | 2.12.5    | 2.13.4 | 2.13.4 | minor | minor   | 160         |                        |
| pydantic-settings | outdated   | 2.12.0    | 2.14.1 | 2.14.1 | minor | minor   | 178         |                        |
| streamlit         | outdated   | 1.53.0    | 1.57.0 | 1.57.0 | minor | minor   | 104         |                        |
| plotly            | outdated   | 6.5.2     | 6.7.0  | 6.7.0  | minor | patch   | 84          |                        |
| python-dotenv     | outdated   | 1.2.1     | 1.2.2  | 1.2.2  | patch | patch   | 126         |                        |
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
