# Contributing

Thank you for your interest in contributing to Cellcom Energy for Home Assistant!

## Reporting Issues

- Use the GitHub issue templates.
- Include: HA version, integration version, and **redacted** logs.
- **Never** paste tokens, phone numbers, ID numbers, or HAR files without sanitising.

## Development Setup

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for full instructions.

## Pull Requests

1. Fork the repository and create a feature branch off `main`.
2. Write tests for any new behaviour.
3. Ensure all checks pass:
   ```bash
   pytest tests/ -v
   ruff check custom_components/
   mypy custom_components/cellcom_energy/
   ```
4. Update `CHANGELOG.md` under the `[Unreleased]` section.
5. Open a PR with a clear title and description.

## Code Style

| Tool | Purpose |
|------|---------|
| `black` | Code formatting |
| `isort` | Import ordering |
| `ruff` | Linting |
| `mypy --strict` | Type checking |

Run pre-commit hooks to enforce style automatically:
```bash
pre-commit install
```

## Sensitive Data

- Never commit credentials, tokens, or HAR files.
- The `_research/` directory is gitignored — use it for local testing only.

## Code of Conduct

Be respectful. We follow the
[Contributor Covenant](https://www.contributor-covenant.org/).
