from pathlib import Path

import pytest

from skillctl.core import (
    Adapter,
    Layout,
    SkillctlError,
    apply_enabled,
    doctor,
    migrate,
    restore,
    scan_adapter,
)


def skill(root: Path, name: str, body: str = "---\nname: test\n---\n") -> Path:
    path = root / name
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(body)
    return path


@pytest.fixture
def layout(tmp_path):
    value = Layout(tmp_path / "home")
    value.initialize()
    return value


def test_init_and_toggle_only_links(layout):
    skill(layout.available, "alpha")
    apply_enabled(layout, {"alpha"})
    link = layout.enabled / "alpha"
    assert link.is_symlink()
    assert link.resolve() == layout.available / "alpha"
    apply_enabled(layout, set())
    assert not link.exists()
    assert (layout.available / "alpha").exists()


def test_init_copies_packaged_adapter_config(layout):
    config = layout.config.read_text()
    assert 'name = "agents"' in config
    assert 'name = "openclaw"' in config
    assert 'name = "claude"' in config
    assert 'name = "codex"' in config
    assert "delegate" not in config
    assert "protected =" not in config


def test_adapters_are_loaded_from_user_config(layout):
    layout.config.write_text(
        """
[[adapters]]
name = "custom"
path = "~/.custom/skills"
""".lstrip()
    )

    assert layout.adapters() == [Adapter("custom", layout.home / ".custom/skills")]


def test_scan_protected_and_broken_link(layout, tmp_path):
    root = tmp_path / "agent"; root.mkdir()
    skill(root, "ok")
    (root / ".system").mkdir()
    (root / "broken").symlink_to(root / "missing")
    items = scan_adapter(layout, Adapter("x", root))
    assert {x.name for x in items} == {"ok", ".system", "broken"}
    assert any(x.issue == "protected system directory" for x in items)
    assert any(x.issue == "broken symlink" for x in items)


def test_migration_delegation_and_restore(layout, tmp_path):
    root = tmp_path / "agent"; root.mkdir(); skill(root, "alpha")
    adapter = Adapter("demo", root)
    assert migrate(layout, adapter, {"alpha"}, lambda *_: "skip", takeover=True) == ["alpha"]
    assert root.is_symlink()
    assert (layout.available / "alpha").is_dir()
    assert (layout.enabled / "alpha").is_symlink()
    restore(layout, adapter)
    assert root.is_dir() and not root.is_symlink()
    assert (root / "alpha" / "SKILL.md").exists()


def test_partial_migration_refuses_delegation(layout, tmp_path):
    root = tmp_path / "agent"; root.mkdir(); skill(root, "one"); skill(root, "two")
    with pytest.raises(SkillctlError, match="partially imported"):
        migrate(layout, Adapter("demo", root), {"one"}, lambda *_: "skip", takeover=True)
    assert root.is_dir() and not root.is_symlink()


def test_migration_refuses_root_with_unmanaged_content(layout, tmp_path):
    root = tmp_path / "agent"; root.mkdir(); skill(root, "one")
    (root / "notes").mkdir()
    with pytest.raises(SkillctlError, match="unmanaged content"):
        migrate(layout, Adapter("demo", root), {"one"}, lambda *_: "skip", takeover=True)
    assert root.is_dir() and not root.is_symlink()


def test_import_only_ignores_unmanaged_content(layout, tmp_path):
    root = tmp_path / "agent"; root.mkdir(); skill(root, "one")
    (root / ".system").mkdir()
    (root / "notes").mkdir()

    assert migrate(layout, Adapter("demo", root), {"one"}, lambda *_: "skip") == ["one"]
    assert root.is_dir() and not root.is_symlink()


def test_skipped_conflict_does_not_delegate(layout, tmp_path):
    root = tmp_path / "agent"; root.mkdir(); skill(root, "same", "source")
    skill(layout.available, "same", "existing")
    assert migrate(
        layout, Adapter("demo", root), {"same"}, lambda *_: "skip", takeover=True
    ) == []
    assert root.is_dir() and not root.is_symlink()


def test_conflict_requires_choice_and_doctor_finds_bad_link(layout, tmp_path):
    root = tmp_path / "agent"; root.mkdir(); skill(root, "same", "one")
    skill(layout.available, "same", "other")
    adapter = Adapter("demo", root)
    assert migrate(layout, adapter, {"same"}, lambda *_: "rename") == ["same-demo"]
    (layout.enabled / "bad").symlink_to("../skills-available/missing")
    assert any("broken enabled symlink" in item for item in doctor(layout))
