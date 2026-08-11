<div align="center">

# agent-skillctl

**One shared skill library for all of your coding agents.**

Manage local agent skills with an Nginx-inspired
**available / enabled** workflow.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/managed%20with-uv-DE5FE9?logo=astral&logoColor=white)](https://docs.astral.sh/uv/)
[![Textual](https://img.shields.io/badge/TUI-Textual-FF2D20)](https://textual.textualize.io/)
[![Ruff](https://img.shields.io/badge/code%20style-Ruff-D7FF64?logo=ruff&logoColor=261230)](https://docs.astral.sh/ruff/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/onewesong/agent-skillctl?style=flat&logo=github)](https://github.com/onewesong/agent-skillctl/stargazers)

[Quick start](#quick-start) · [How it works](#how-it-works) · [Usage](#usage) · [Configuration](#configuration) · [Development](#development)

</div>

---

`skillctl` keeps one canonical copy of every skill and uses symlinks to control
which skills your agents can see. Import once, enable or disable once, and every
linked agent follows the same active skill set.

## Why agent-skillctl?

Agent tools commonly keep skills in separate directories such as
`~/.agents/skills` and `~/.claude/skills`. Copying the same skill into each
location creates duplicates that drift over time and makes it difficult to know
which version is active.

`agent-skillctl` gives you:

- **One source of truth** — canonical skill copies live in
  `~/.agents/skills-available`.
- **Instant toggles** — enable or disable skills through a symlink-based active
  view without deleting their source files.
- **A visual manager** — browse, import, enable, and disable skills from a
  keyboard- and mouse-friendly TUI.
- **Safe imports** — validate skill directories, detect conflicts, verify copied
  content, and reject unsafe symlinks.
- **Recoverable takeovers** — connect compatible agent roots to the shared view
  while preserving restorable backups.
- **Built-in diagnostics** — inspect skills, adapters, broken links, and layout
  health with one command.

## Quick start

### Requirements

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) for the recommended installation flow

### Install

```bash
uv tool install agent-skillctl
```

Install from a local checkout instead:

```bash
uv tool install .
```

Both executable names launch the same CLI:

```bash
skillctl
# or
agent-skillctl
```

Run `skillctl` in an interactive terminal to open the manager. On first launch,
an empty library opens directly on **Scan & Import** so you can discover existing
skills.

## How it works

The directory layout follows the same idea as Nginx's
`sites-available` / `sites-enabled` model:

```text
~/.agents/
├── skills-available/  # Canonical skill directories
├── skills/            # Symlinks for the currently enabled skills
├── backups/           # Recoverable backups created before takeover
├── config.toml        # Adapter configuration
├── registry.toml      # Import sources, timestamps, and content hashes
└── .skill-lock.json   # Existing npx skills metadata, preserved when present
```

```text
Existing agent roots       Canonical library              Enabled view

~/.claude/skills ───┐      ~/.agents/skills-available/     ~/.agents/skills/
~/.other/skills ────┴─▶    ├── skill-a/          ───────▶  ├── skill-a -> ../skills-available/skill-a
       import               └── skill-b/          ───────▶  └── skill-b -> ../skills-available/skill-b
                                                             ▲
Compatible agent roots ─────────────── optional takeover ────┘
```

The canonical directory is never removed when a skill is disabled. Applying a
new enabled set is transactional: `skillctl` builds a complete staged symlink
view before replacing the previous one.

> [!NOTE]
> `skillctl` complements rather than replaces download tools such as
> `npx skills`. Version 1 organizes skills already present on your machine and
> records where they came from.

## Usage

### Interactive manager

```bash
skillctl
```

The TUI has two main views:

- **Choose** — press <kbd>Space</kbd> to stage enable/disable changes, then
  <kbd>Enter</kbd> or select **Apply** to commit them.
- **Scan & Import** — review configured adapters, inspect discovered skills, and
  choose an import mode.

Switch tabs with <kbd>1</kbd> and <kbd>2</kbd> or click them. Press <kbd>q</kbd>
to exit.

### Commands

| Command | Description |
| --- | --- |
| `skillctl` | Open the interactive manager; print diagnostics when non-interactive |
| `skillctl import` | Open the manager directly on **Scan & Import** |
| `skillctl import -y` | Import valid skills from every adapter without prompts |
| `skillctl import <adapter> -y` | Import valid skills from one adapter without prompts |
| `skillctl check` | Show enabled skills, adapter status, and health diagnostics |
| `skillctl restore <adapter>` | Restore the latest backup for a taken-over adapter |

Use `skillctl --help` or `skillctl <command> --help` for the full CLI reference.

### Import modes

| Mode | Behavior |
| --- | --- |
| **Import only** | Copy valid skills into the shared library and leave the source root untouched |
| **Import + takeover** | Import skills, back up the source root, and replace it with a link to the shared enabled view |

Takeover is offered only when the entire source root is safe. Protected content,
invalid directories, broken links, partial imports, or symlinks escaping the
skill directory prevent takeover. The central `agents` adapter can never take
itself over.

When a skill name already exists with different content, the interactive flow
lets you skip it, rename the imported copy, or overwrite the canonical copy
after creating a backup.

## Configuration

Built-in adapters are packaged in `src/skillctl/config.toml`. During first-time
initialization, `skillctl` copies that configuration to
`~/.agents/config.toml`; from then on, your local copy is authoritative.

Add an agent by defining its skill root:

```toml
[[adapters]]
name = "my-agent"
path = "~/.my-agent/skills"
```

Adapter configuration only describes where skills live. You choose between
**Import only** and **Import + takeover** at import time.

## Safety model

- Existing non-skill files under `~/.agents/` are left untouched.
- Codex `.system` and bundled content are ignored during import and block
  takeover of that root.
- Imports are copied through a staging directory and verified with content
  hashes before being registered.
- Skills containing symlinks that escape their own source directory are
  rejected.
- Conflicting canonical copies are backed up before an overwrite.
- Disabling a skill only removes its active symlink, never its canonical copy.

## Development

Clone the repository and install all dependency groups:

```bash
git clone https://github.com/onewesong/agent-skillctl.git
cd agent-skillctl
uv sync --all-groups
```

Run the quality checks:

```bash
uv run pytest
uv run ruff check .
uv run mypy
```

For isolated manual testing, provide a temporary home directory:

```bash
uv run skillctl --home /tmp/skillctl-home
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for the architecture and verification
workflow, and [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.

## Contributing

Issues, documentation improvements, adapters, and tests are welcome. Please
include coverage for both success and rollback paths when adding behavior.

## License

Distributed under the [MIT License](LICENSE).
