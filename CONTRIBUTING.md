# Contributing

Issues, documentation fixes, adapters, and tests are welcome. Work in an isolated environment so tests never touch your real HOME:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run mypy
```

Before submitting a change, ensure that tests and Ruff pass. New behavior should cover both success and failure/rollback paths, and must not automatically delete canonical skill copies. When adding an adapter, document its native skill root, whether it contains system content, and whether whole-directory takeover can ever be safe.

This project is licensed under MIT. By contributing, you agree to publish your contribution under the same license.
