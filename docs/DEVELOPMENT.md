# Development Guide

## Prerequisites

- Python 3.12+
- Git
- [VS Code](https://code.visualstudio.com/) with the Remote - Containers extension
  (recommended) **or** a local Home Assistant Core dev environment

---

## Quick Start with VS Code Devcontainer (Recommended)

```bash
git clone https://github.com/your-user/hass-cellcom-energy
cd hass-cellcom-energy
code .
```

When VS Code asks: **"Reopen in Container"** → yes.
This gives you a full HA dev environment with all dependencies pre-installed.

Press **F5** (or use the Run & Debug panel → `"Home Assistant: Debug"`)
to start HA at `http://localhost:8123`.

---

## Local Setup (Without Devcontainer)

```bash
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

---

## Running Tests

```bash
# Full test suite with coverage
pytest tests/ -v --cov=custom_components.cellcom_energy --cov-report=term-missing

# Fast run (skip slow integration tests)
pytest tests/unit/ -v

# Single test file
pytest tests/test_api.py -v
```

---

## Code Quality

```bash
# Format
black custom_components/ tests/

# Sort imports
isort custom_components/ tests/

# Lint
ruff check custom_components/

# Type check
mypy custom_components/cellcom_energy/ --strict
```

Install pre-commit hooks to run these automatically on every commit:

```bash
pip install pre-commit
pre-commit install
```

---

## Validating for HACS / hassfest

```bash
# hassfest (checks manifest.json, strings, etc.)
python -m script.hassfest

# HACS validation
pip install hacs-action
hacs-action validate
```

Both are also run automatically in CI (see `.github/workflows/validate.yml`).

---

## Debugging in HA

Add to your `configuration.yaml` during development:

```yaml
logger:
  default: warning
  logs:
    custom_components.cellcom_energy: debug
    custom_components.cellcom_energy.api: debug
```

---

## Capturing New API Endpoints

When Cellcom adds new features, capture them with:

1. Open Chrome → DevTools → **Network** tab
2. Enable **Preserve log**
3. Clear the list
4. Navigate to the target screen in the Cellcom portal
5. Wait for all XHR requests to finish
6. Right-click → **Save all as HAR with content**
7. Sanitise with [cloudflare/har-sanitizer](https://github.com/cloudflare/har-sanitizer)
8. Save to `_research/` (gitignored — never commit HAR files)

---

## Project Structure

```
hass-cellcom-energy/
├── custom_components/
│   └── cellcom_energy/
│       ├── __init__.py          # Entry setup and unload
│       ├── api.py               # HTTP client, auth, data endpoints
│       ├── binary_sensor.py     # Binary sensor entities
│       ├── config_flow.py       # Config and reauth flows
│       ├── const.py             # Domain, endpoints, defaults
│       ├── coordinator.py       # DataUpdateCoordinator
│       ├── exceptions.py        # Custom exception classes
│       ├── manifest.json        # Integration metadata
│       ├── models.py            # Typed dataclasses
│       ├── sensor.py            # Sensor entities
│       ├── strings.json         # English strings (base)
│       └── translations/
│           ├── en.json
│           └── he.json
├── tests/
│   ├── conftest.py
│   ├── fixtures/                # Recorded API responses (anonymised)
│   ├── test_api.py
│   ├── test_config_flow.py
│   └── test_coordinator.py
├── docs/
│   ├── API_REFERENCE.md
│   ├── ARCHITECTURE.md
│   ├── AUTH_FLOW.md
│   ├── DEVELOPMENT.md           # (this file)
│   ├── ENTITIES.md
│   └── IMPLEMENTATION_PLAN.md
├── .github/
│   └── workflows/
│       └── validate.yml
├── .vscode/
│   └── launch.json
├── _research/                   # gitignored — HAR files, curl tests
├── hacs.json
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
└── LICENSE
```

---

## Release Checklist

1. Update version in `custom_components/cellcom_energy/manifest.json`
2. Update `CHANGELOG.md` (move items from Unreleased to new version)
3. Commit: `git commit -m "chore: release vX.Y.Z"`
4. Tag: `git tag vX.Y.Z && git push --tags`
5. GitHub Actions creates the Release automatically
