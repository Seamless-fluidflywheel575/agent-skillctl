# agent-skillctl

`skillctl` manages local agent skills from `~/.agents/` using the Nginx-inspired **sites-available / sites-enabled** model: keep one canonical copy of each skill and use symlinks to decide which skills agents can see.

```text
~/.agents/
├── skills-available/  # Canonical skill copies
├── skills/            # Symlinks for the enabled skill set (the only enabled view)
├── backups/           # Recoverable backups made before taking over an agent root
├── config.toml        # skillctl adapter configuration
├── registry.toml      # Import sources and content hashes
└── .skill-lock.json   # Preserved npx skills metadata, when present
```

## Why

Agents often use separate directories such as `~/.agents/skills`, `~/.claude/skills`, and others. Copy-based installation drifts over time, and disabling a skill for one agent does not update the rest. skillctl stores copies in `~/.agents/skills-available`, builds an agent-visible symlink view in `~/.agents/skills`, and can take over compatible external agent roots with a link to that view. Toggle once, and every linked agent follows the same enabled set.

skillctl does not replace the download workflow of `npx skills`: v1 only organizes skills already present on the local machine and records their source paths. Existing non-skill files in `~/.agents/`, including `.skill-lock.json`, are left alone. Codex's `.system` and bundled content are ignored during import and prevent its root from being taken over.

## Quick start

```bash
uv tool install agent-skillctl
agent-skillctl        # Same command as skillctl
skillctl              # Import, enable, or disable skills in one UI
skillctl check        # Status and diagnostics in one view
```

When installing from a local checkout, use `uv tool install .`. Both
`agent-skillctl` and `skillctl` invoke the same CLI.

All commands initialize the shared layout automatically. On an interactive terminal, running `skillctl`
opens a two-tab manager. An empty library starts on **Scan & Import**; once skills have been imported,
later launches start on **Choose**. Use `1` and `2` or click the tabs to switch. In redirected or
non-interactive environments, the same command prints the `check` view instead.

The **Scan & Import** tab lists every configured adapter, its source, available skills, and ignored content. Select **Import only** to copy valid skills while leaving the source untouched, or **Import + takeover** to replace a completely safe external root with a link to the shared enabled view. Conflicts open a dialog for skip, rename, or overwrite. The `agents` adapter can never take itself over.

`skillctl import` remains as a shortcut that starts on the **Scan & Import** tab. For automation, `skillctl import -y` performs the safe import-only mode and skips conflicts. Use `skillctl restore claude` to undo a takeover.

## TUI

Run `skillctl`. In **Choose**, Space stages an enable/disable change and Enter or **Apply** commits it. In **Scan & Import**, Enter imports from the selected adapter. Press `q` to exit. The TUI never deletes a canonical skill copy.

## Configure adapters

Built-in adapters are defined by the packaged `src/skillctl/config.toml`. On first initialization,
skillctl copies that file to `~/.agents/config.toml`; from then on, the user copy is authoritative.
Add or edit an adapter there like this:

```toml
[[adapters]]
name = "my-agent"
path = "~/.my-agent/skills"
```

Adapter configuration only describes where skills live. Import-only versus directory takeover is selected interactively at import time. Protected or invalid entries such as `.system` are ignored for import-only mode and automatically disable takeover for that root.

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run mypy
```

See [DEVELOPMENT.md](DEVELOPMENT.md) and [CONTRIBUTING.md](CONTRIBUTING.md).
