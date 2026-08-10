# Development guide

## Architecture

- `core.py`: layout, scanning, import, backup/restore, symlink transactions, and diagnostics.
- `config.toml`: packaged defaults for built-in adapters; copied to the user layout on initialization.
- `cli.py`: standard-library `argparse` command entry point.
- `tui.py`: Textual interface that only commits enabled-link state.

## Run locally

```bash
uv sync --all-groups
uv run skillctl --home /tmp/skillctl-home
uv run skillctl --home /tmp/skillctl-home check
uv run skillctl
```

`--home` provides an isolated HOME for tests and manual verification. Import copies into a temporary directory inside `~/.agents` and verifies the content hash. Enable/disable builds a complete link view in a staging directory and then replaces the prior view. Exceptions must never delete canonical directories in `skills-available`.

Import is handled by the **Scan & Import** tab. Empty layouts start there; layouts with available skills start on **Choose**. The import tab reviews configured adapters, offers import-only or safe takeover, and opens a conflict-policy dialog when needed. The built-in `agents` adapter can never take itself over. `skillctl import -y` is the non-interactive import-only path.

## Verification checklist

1. Create a skill containing `SKILL.md` in a temporary directory.
2. After import, verify that available is a real directory and skills is a relative symlink.
3. Disable the skill and confirm that its canonical directory remains.
4. Run restore and confirm that the agent root becomes a regular directory again.
5. Add a broken enabled link manually and confirm that `check` reports it.
