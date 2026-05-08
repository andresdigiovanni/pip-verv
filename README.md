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

## Example JSON Output

```json
{
  "score": 86.2,
  "generated_at": "2026-05-05T09:28:08.576154",
  "dependencies": [
    {
      "name": "pyarrow",
      "status": "outdated",
      "installed": "23.0.0",
      "latest": "24.0.0",
      "target": "24.0.0",
      "bump": "major",
      "urgency": "minor",
      "days_behind": 92,
      "blockers": []
    },
    {
      "name": "pandas",
      "status": "outdated",
      "installed": "2.3.3",
      "latest": "3.0.2",
      "target": null,
      "bump": "major",
      "urgency": "minor",
      "days_behind": 182,
      "blockers": ["streamlit (<3,>=1.4.0)"]
    }
    // ...
  ]
}
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
