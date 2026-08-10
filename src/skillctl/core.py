from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path


class SkillctlError(RuntimeError):
    pass


@dataclass(frozen=True)
class Adapter:
    name: str
    path: Path


@dataclass(frozen=True)
class Skill:
    name: str
    path: Path
    adapter: str | None = None
    enabled: bool = False
    issue: str | None = None


@dataclass(frozen=True)
class Layout:
    home: Path

    @property
    def root(self) -> Path:
        return self.home / ".agents"

    @property
    def available(self) -> Path:
        return self.root / "skills-available"

    @property
    def enabled(self) -> Path:
        return self.root / "skills"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def config(self) -> Path:
        return self.root / "config.toml"

    @property
    def registry(self) -> Path:
        return self.root / "registry.toml"

    @classmethod
    def default(cls) -> Layout:
        return cls(Path.home())

    def initialize(self) -> None:
        for directory in (self.root, self.available, self.enabled, self.backups):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.config.exists():
            self.config.write_text(default_config(), encoding="utf-8")
        if not self.registry.exists():
            self.registry.write_text("# Imported skill metadata\n", encoding="utf-8")

    def adapters(self) -> list[Adapter]:
        config = self.config.read_text(encoding="utf-8") if self.config.exists() else default_config()
        data = tomllib.loads(config)
        raw_adapters = data.get("adapters", [])
        if not isinstance(raw_adapters, list):
            raise SkillctlError("config.toml adapters must be an array")
        adapters: list[Adapter] = []
        for raw in raw_adapters:
            if not isinstance(raw, dict):
                raise SkillctlError("each adapter must be a TOML table")
            name, path = raw.get("name"), raw.get("path")
            if not isinstance(name, str) or not isinstance(path, str):
                raise SkillctlError("adapter must contain string name and path values")
            adapters.append(Adapter(name, self._resolve_adapter_path(path)))
        return adapters

    def _resolve_adapter_path(self, raw_path: str) -> Path:
        """Resolve `~/…` against Layout.home so --home remains fully isolated."""
        if raw_path == "~":
            return self.home
        if raw_path.startswith("~/"):
            return self.home / raw_path[2:]
        return Path(raw_path).expanduser()


def default_config() -> str:
    """Return the packaged adapter configuration used to bootstrap new layouts."""
    return files("skillctl").joinpath("config.toml").read_text(encoding="utf-8")


def is_skill(path: Path) -> bool:
    return path.is_dir() and (path / "SKILL.md").is_file()


def content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(path.rglob("*")):
        relative = entry.relative_to(path).as_posix().encode()
        digest.update(relative)
        if entry.is_symlink():
            digest.update(b"L" + os.readlink(entry).encode())
        elif entry.is_file():
            digest.update(b"F" + entry.read_bytes())
    return digest.hexdigest()


def escapes_source(path: Path) -> bool:
    root = path.resolve()
    for entry in path.rglob("*"):
        if entry.is_symlink():
            try:
                entry.resolve().relative_to(root)
            except ValueError:
                return True
    return False


def enabled_names(layout: Layout) -> set[str]:
    if not layout.enabled.exists():
        return set()
    return {entry.name for entry in layout.enabled.iterdir() if entry.is_symlink() and entry.exists()}


def scan_adapter(layout: Layout, adapter: Adapter) -> list[Skill]:
    if not adapter.path.exists() and not adapter.path.is_symlink():
        return [Skill(adapter.name, adapter.path, adapter.name, issue="skill root does not exist")]
    result: list[Skill] = []
    for entry in sorted(adapter.path.iterdir()):
        if entry.name == ".system":
            result.append(Skill(entry.name, entry, adapter.name, issue="protected system directory"))
        elif is_skill(entry):
            issue = "skill contains a symlink escaping its source directory" if escapes_source(entry) else None
            result.append(Skill(entry.name, entry, adapter.name, entry.name in enabled_names(layout), issue))
        elif entry.is_symlink() and not entry.exists():
            result.append(Skill(entry.name, entry, adapter.name, issue="broken symlink"))
        elif entry.is_dir():
            result.append(Skill(entry.name, entry, adapter.name, issue="directory does not contain SKILL.md"))
    return result


def available_skills(layout: Layout) -> list[Skill]:
    if not layout.available.exists():
        return []
    enabled = enabled_names(layout)
    return [Skill(p.name, p, enabled=p.name in enabled,
                  issue=None if is_skill(p) else "directory does not contain SKILL.md")
            for p in sorted(layout.available.iterdir()) if p.is_dir()]


def apply_enabled(layout: Layout, desired: set[str], *, bootstrap: bool = False) -> None:
    candidates = {skill.name: skill.path for skill in available_skills(layout) if skill.issue is None}
    unknown = desired - candidates.keys()
    if unknown:
        raise SkillctlError(f"unknown or invalid skill: {', '.join(sorted(unknown))}")
    if not bootstrap and any(not item.is_symlink() for item in layout.enabled.iterdir()):
        raise SkillctlError("enabled directory may contain only skillctl-managed symlinks")
    stage = Path(tempfile.mkdtemp(prefix=".skills-stage-", dir=layout.root))
    try:
        for name in desired:
            target = os.path.relpath(candidates[name], stage)
            (stage / name).symlink_to(target, target_is_directory=True)
        previous = layout.root / ".skills-previous"
        if previous.exists() or previous.is_symlink():
            raise SkillctlError("unfinished previous transaction found; run skillctl check first")
        os.replace(layout.enabled, previous)
        try:
            os.replace(stage, layout.enabled)
        except Exception:
            os.replace(previous, layout.enabled)
            raise
        shutil.rmtree(previous)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def write_registry(layout: Layout, name: str, source: Path, digest: str) -> None:
    data: dict = {}
    if layout.registry.exists():
        data = tomllib.loads(layout.registry.read_text(encoding="utf-8"))
    entries = data.setdefault("skills", {})
    entries[name] = {"source": str(source), "hash": digest,
                     "imported_at": datetime.now(UTC).isoformat()}
    lines = ["# Imported skill metadata", "[skills]"]
    for key, value in sorted(entries.items()):
        lines.append(f'[skills."{key}"]')
        for field in ("source", "hash", "imported_at"):
            escaped = value[field].replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{field} = "{escaped}"')
    layout.registry.write_text("\n".join(lines) + "\n", encoding="utf-8")


ConflictChoice = Callable[[Skill, Path], str]


def migrate(
    layout: Layout,
    adapter: Adapter,
    names: set[str],
    choose_conflict: ConflictChoice,
    *,
    takeover: bool = False,
) -> list[str]:
    report = scan_adapter(layout, adapter)
    unsafe = [x for x in report if x.issue is not None]
    if takeover and adapter.path == layout.enabled:
        raise SkillctlError("cannot take over the central enabled skill directory")
    if takeover and unsafe:
        raise SkillctlError(
            "skill root contains unmanaged content; refusing takeover: "
            + ", ".join(f"{x.name} ({x.issue})" for x in unsafe)
        )
    scanned = [x for x in report if x.issue is None and x.path.is_dir()]
    selected = [x for x in scanned if x.name in names]
    missing = names - {x.name for x in selected}
    if missing:
        raise SkillctlError(f"cannot import: {', '.join(sorted(missing))}")
    unselected = {x.name for x in scanned} - names
    if takeover and unselected:
        raise SkillctlError("cannot take over a partially imported root: " + ", ".join(sorted(unselected)))
    if takeover and not selected:
        raise SkillctlError("cannot take over a root with no importable skills")
    imported: list[str] = []
    skipped = False
    for skill in selected:
        if escapes_source(skill.path):
            raise SkillctlError(f"{skill.name} contains a symlink escaping its source directory")
        destination = layout.available / skill.name
        final_name = skill.name
        if destination.exists():
            if content_hash(destination) == content_hash(skill.path):
                imported.append(final_name)
                continue
            action = choose_conflict(skill, destination)
            if action == "skip":
                skipped = True
                continue
            if action == "rename":
                final_name = f"{skill.name}-{adapter.name}"
                destination = layout.available / final_name
                if destination.exists():
                    raise SkillctlError(f"renamed destination already exists: {final_name}")
            elif action == "overwrite":
                conflict_backup = layout.backups / "conflicts" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                conflict_backup.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), conflict_backup / destination.name)
            else:
                raise SkillctlError("conflict action must be skip, rename, or overwrite")
        staging_parent = Path(tempfile.mkdtemp(prefix=".migrate-", dir=layout.root))
        try:
            staged = staging_parent / final_name
            shutil.copytree(skill.path, staged, symlinks=True)
            if not is_skill(staged) or content_hash(staged) != content_hash(skill.path):
                raise SkillctlError(f"copy verification failed: {skill.name}")
            shutil.move(str(staged), destination)
            write_registry(layout, final_name, skill.path, content_hash(destination))
            imported.append(final_name)
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)
    if imported:
        apply_enabled(
            layout,
            enabled_names(layout) | set(imported),
            bootstrap=adapter.path == layout.enabled,
        )
    # A skipped conflict leaves the original root authoritative for that skill;
    # never hide it by taking over the complete root in that case.
    if takeover and not skipped:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = layout.backups / stamp / adapter.name
        backup.parent.mkdir(parents=True)
        adapter.path.rename(backup)
        adapter.path.symlink_to(layout.enabled, target_is_directory=True)
    return imported


def restore(layout: Layout, adapter: Adapter, stamp: str | None = None) -> Path:
    if not adapter.path.is_symlink():
        raise SkillctlError("adapter is not currently taken over by skillctl")
    choices = sorted((layout.backups / stamp).glob(adapter.name)) if stamp else sorted(layout.backups.glob(f"*/{adapter.name}"))
    if not choices:
        raise SkillctlError("no restorable backup found")
    backup = choices[-1]
    adapter.path.unlink()
    shutil.move(str(backup), adapter.path)
    return backup


def doctor(layout: Layout) -> list[str]:
    issues: list[str] = []
    for directory in (layout.available, layout.enabled):
        if not directory.exists():
            issues.append(f"missing directory: {directory}")
    if layout.enabled.exists():
        for entry in layout.enabled.iterdir():
            if not entry.is_symlink():
                issues.append(f"enabled directory contains a non-symlink: {entry.name}")
            elif not entry.exists():
                issues.append(f"broken enabled symlink: {entry.name}")
            elif entry.resolve().parent != layout.available.resolve():
                issues.append(f"enabled symlink does not point to available: {entry.name}")
    if (layout.root / ".skills-previous").exists():
        issues.append("unfinished enable transaction: .skills-previous")
    return issues
