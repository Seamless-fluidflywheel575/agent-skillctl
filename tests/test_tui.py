import asyncio

from textual.widgets import Button, TabbedContent

from skillctl.core import Layout
from skillctl.tui import ConflictScreen, ImportPanel, SkillctlApp, SkillList


def test_tui_stages_then_applies_enabled_link(tmp_path):
    layout = Layout(tmp_path / "home")
    layout.initialize()
    skill = layout.available / "alpha"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# alpha\n")

    async def exercise() -> None:
        app = SkillctlApp(layout)
        async with app.run_test() as pilot:
            assert app.query_one(TabbedContent).active == "choose-tab"
            assert app.query_one("#apply", Button).disabled
            await pilot.press("space")
            assert "alpha" in app.desired
            assert not (layout.enabled / "alpha").exists()
            assert not app.query_one("#apply", Button).disabled
            await pilot.press("enter")
            assert (layout.enabled / "alpha").is_symlink()
            assert app.query_one("#apply", Button).disabled

    asyncio.run(exercise())


def test_tui_import_can_take_over_safe_adapter(tmp_path):
    layout = Layout(tmp_path / "home")
    layout.initialize()
    layout.config.write_text('[[adapters]]\nname = "demo"\npath = "~/.demo/skills"\n')
    root = layout.home / ".demo/skills"
    skill = root / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# alpha\n")

    async def exercise() -> None:
        app = SkillctlApp(layout)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one(TabbedContent).active == "import-tab"
            assert app.query_one(ImportPanel)
            await pilot.press("t")
            await pilot.pause()
            assert root.is_symlink()
            assert (layout.available / "alpha").is_dir()

    asyncio.run(exercise())


def test_tui_can_start_in_import_panel(tmp_path):
    layout = Layout(tmp_path / "home")
    layout.initialize()

    async def exercise() -> None:
        app = SkillctlApp(layout, start_import=True, initial_adapter="codex")
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one(TabbedContent).active == "import-tab"
            assert app.query_one(ImportPanel).cursor == 3

    asyncio.run(exercise())


def test_tui_import_only_ignores_unsafe_content(tmp_path):
    layout = Layout(tmp_path / "home")
    layout.initialize()
    layout.config.write_text('[[adapters]]\nname = "demo"\npath = "~/.demo/skills"\n')
    root = layout.home / ".demo/skills"
    skill = root / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# alpha\n")
    (root / ".system").mkdir()

    async def exercise() -> None:
        app = SkillctlApp(layout)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one(TabbedContent).active == "import-tab"
            await pilot.press("i")
            await pilot.pause()
            assert root.is_dir() and not root.is_symlink()
            assert (layout.available / "alpha").is_dir()

    asyncio.run(exercise())


def test_tui_import_conflict_can_rename(tmp_path):
    layout = Layout(tmp_path / "home")
    layout.initialize()
    layout.config.write_text('[[adapters]]\nname = "demo"\npath = "~/.demo/skills"\n')
    source = layout.home / ".demo/skills/alpha"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("source\n")
    existing = layout.available / "alpha"
    existing.mkdir()
    (existing / "SKILL.md").write_text("existing\n")

    async def exercise() -> None:
        app = SkillctlApp(layout)
        async with app.run_test() as pilot:
            await pilot.press("i")
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()
            assert isinstance(app.screen, ConflictScreen)
            await pilot.press("r")
            await pilot.pause()
            assert app.query_one(TabbedContent).active == "import-tab"
            assert (layout.available / "alpha-demo").is_dir()

    asyncio.run(exercise())


def test_choose_list_scrolls_with_cursor(tmp_path):
    layout = Layout(tmp_path / "home")
    layout.initialize()
    for index in range(30):
        skill = layout.available / f"skill-{index:02d}"
        skill.mkdir()
        (skill / "SKILL.md").write_text(f"# skill {index}\n")

    async def exercise() -> None:
        app = SkillctlApp(layout)
        async with app.run_test(size=(60, 16)) as pilot:
            await pilot.press(*(["down"] * 20))
            await pilot.pause()
            skills = app.query_one("#skills", SkillList)
            assert app.cursor == 20
            assert skills.scroll_y > 0
            selected_y = app.cursor + 2
            assert skills.scroll_y <= selected_y < skills.scroll_y + skills.scrollable_content_region.height

            await pilot.press(*(["up"] * 20))
            await pilot.pause()
            assert app.cursor == 0
            assert skills.scroll_y <= 2

    asyncio.run(exercise())


def test_choose_list_uses_laid_out_width_on_first_render(tmp_path):
    layout = Layout(tmp_path / "home")
    layout.initialize()
    name = "improve-codebase-architecture"
    skill = layout.available / name
    skill.mkdir()
    (skill / "SKILL.md").write_text(f"# {name}\n")

    async def exercise() -> None:
        app = SkillctlApp(layout)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            skills = app.query_one("#skills", SkillList)
            rendered = "\n".join(line.text for line in skills.lines)
            assert name in rendered

    asyncio.run(exercise())
