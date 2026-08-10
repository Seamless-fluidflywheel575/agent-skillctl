from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from rich import box
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.geometry import Region
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, RichLog, Static, TabbedContent, TabPane

from .core import (
    Adapter,
    Layout,
    SkillctlError,
    apply_enabled,
    available_skills,
    content_hash,
    enabled_names,
    migrate,
    scan_adapter,
)


class SkillList(RichLog):
    can_focus = True
    BINDINGS: ClassVar = [
        Binding("up,k", "app.up", show=False),
        Binding("down,j", "app.down", show=False),
    ]

    def update(self, content) -> None:
        self.clear()
        self.write(content, expand=True, scroll_end=False)


def display_path(layout: Layout, path: Path) -> str:
    try:
        relative = path.relative_to(layout.home)
    except ValueError:
        return str(path)
    return "~" if not relative.parts else f"~/{relative}"


class ConflictScreen(ModalScreen[str | None]):
    BINDINGS: ClassVar = [
        ("s", "choose_skip", "Skip"),
        ("r", "choose_rename", "Rename"),
        ("o", "choose_overwrite", "Overwrite"),
        ("escape", "cancel", "Cancel"),
    ]
    DEFAULT_CSS = """
    ConflictScreen {
        align: center middle;
        background: $background 70%;
    }

    #conflict-dialog {
        width: 68;
        height: auto;
        padding: 1 2;
        border: round $warning;
        background: $surface;
    }

    #conflict-title {
        text-style: bold;
        color: $warning;
    }

    #conflict-copy {
        height: 4;
        margin-top: 1;
        color: $text-muted;
    }

    #conflict-actions {
        height: 3;
        align: right middle;
    }

    #conflict-actions Button {
        width: auto;
        min-width: 10;
        margin-left: 1;
    }
    """

    def __init__(self, count: int) -> None:
        super().__init__()
        self.count = count

    def compose(self) -> ComposeResult:
        with Vertical(id="conflict-dialog"):
            yield Label(f"{self.count} conflicting skill(s)", id="conflict-title")
            yield Static(
                "Choose one policy for existing skills. Overwrite creates a recoverable backup.",
                id="conflict-copy",
            )
            with Horizontal(id="conflict-actions"):
                yield Button("Skip", id="conflict-skip")
                yield Button("Rename", id="conflict-rename", variant="primary")
                yield Button("Overwrite", id="conflict-overwrite", variant="warning")
                yield Button("Cancel", id="conflict-cancel")

    def action_choose_skip(self) -> None:
        self.dismiss("skip")

    def action_choose_rename(self) -> None:
        self.dismiss("rename")

    def action_choose_overwrite(self) -> None:
        self.dismiss("overwrite")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        choices = {
            "conflict-skip": "skip",
            "conflict-rename": "rename",
            "conflict-overwrite": "overwrite",
        }
        button_id = event.button.id
        self.dismiss(choices.get(button_id) if button_id is not None else None)


class ImportPanel(Vertical):
    class Imported(Message):
        def __init__(self, names: list[str]) -> None:
            super().__init__()
            self.names = names

    DEFAULT_CSS = """
    #import-panel {
        height: 1fr;
    }

    #import-title {
        height: 2;
        text-style: bold;
    }

    #adapters {
        height: 1fr;
        padding: 0 1;
        border: round $primary-background;
        background: $surface;
        overflow-y: auto;
        scrollbar-size-vertical: 1;
        scrollbar-color: $primary-background;
        scrollbar-color-hover: $primary;
    }

    #adapters:focus {
        border: round $primary;
    }

    #import-detail {
        height: 4;
        padding: 0 1;
        border-left: thick $primary;
        background: $panel;
        color: $text-muted;
    }

    #import-actions {
        height: 3;
        align: right middle;
    }

    #import-actions Button {
        width: auto;
        min-width: 14;
        margin-left: 1;
    }
    """

    def __init__(self, layout: Layout, initial_adapter: str | None = None) -> None:
        super().__init__(id="import-panel")
        self.skill_layout = layout
        self.adapters = layout.adapters()
        self.cursor = next(
            (
                index
                for index, adapter in enumerate(self.adapters)
                if adapter.name == initial_adapter
            ),
            0,
        )

    def compose(self) -> ComposeResult:
        yield Label("Scan configured adapters and import their skills", id="import-title")
        yield SkillList(id="adapters", min_width=1, wrap=False, auto_scroll=False)
        yield Static("", id="import-detail", markup=False)
        with Horizontal(id="import-actions"):
            yield Button("Import only", id="import-only", variant="primary")
            yield Button("Import + takeover", id="takeover", variant="warning")

    def on_mount(self) -> None:
        self.refresh_view()

    def adapter_state(self, adapter: Adapter) -> tuple[list, list, bool, str]:
        if not adapter.path.exists() and not adapter.path.is_symlink():
            return [], [], False, "Missing"
        if (
            adapter.path.is_symlink()
            and adapter.path.resolve() == self.skill_layout.enabled.resolve()
        ):
            return [], [], False, "Taken over"
        report = scan_adapter(self.skill_layout, adapter)
        valid = [item for item in report if item.issue is None]
        issues = [item for item in report if item.issue is not None]
        takeover = adapter.path != self.skill_layout.enabled and bool(valid) and not issues
        status = f"{len(valid)} skill(s)" if valid else "No skills"
        if valid and issues:
            status = f"{len(valid)} + {len(issues)} ignored"
        return valid, issues, takeover, status

    def refresh_view(self) -> None:
        table = Table(box=box.SIMPLE, expand=True, pad_edge=False)
        table.add_column("", width=2, no_wrap=True)
        table.add_column("Adapter", ratio=1)
        table.add_column("Source", ratio=2)
        table.add_column("Status", width=18, justify="right", no_wrap=True)
        for index, adapter in enumerate(self.adapters):
            _, _, _, status = self.adapter_state(adapter)
            selected = index == self.cursor
            table.add_row(
                Text("›" if selected else " ", style="bold cyan"),
                Text(adapter.name, style="bold" if selected else ""),
                Text(display_path(self.skill_layout, adapter.path), style="dim"),
                Text(status, style="yellow" if status == "Missing" else ""),
                style="on #263445" if selected else None,
            )
        self.query_one("#adapters", SkillList).update(table)
        self.call_after_refresh(self.scroll_cursor_into_view)

        if not self.adapters:
            self.query_one("#import-detail", Static).update("No adapters configured.")
            self.update_buttons([], False)
            return
        adapter = self.adapters[self.cursor]
        valid, issues, takeover, status = self.adapter_state(adapter)
        detail = Text()
        detail.append(adapter.name, style="bold")
        detail.append(f"  ·  {status}\n", style="dim")
        detail.append(display_path(self.skill_layout, adapter.path), style="dim")
        if issues:
            detail.append("\nIgnored: ", style="yellow")
            detail.append(", ".join(item.name for item in issues), style="yellow")
        if valid and not takeover:
            detail.append("\nTakeover unavailable for this source.", style="dim")
        self.query_one("#import-detail", Static).update(detail)
        self.update_buttons(valid, takeover)

    def scroll_cursor_into_view(self) -> None:
        self.query_one("#adapters", SkillList).scroll_to(
            y=max(0, self.cursor - 2),
            animate=False,
            immediate=True,
            force=True,
        )

    def update_buttons(self, valid: list, takeover: bool) -> None:
        self.query_one("#import-only", Button).disabled = not valid
        self.query_one("#takeover", Button).disabled = not takeover

    def action_up(self) -> None:
        if self.cursor > 0:
            self.cursor -= 1
            self.refresh_view()

    def action_down(self) -> None:
        if self.cursor < len(self.adapters) - 1:
            self.cursor += 1
            self.refresh_view()

    def action_import_only(self) -> None:
        self.begin_import(takeover=False)

    def action_takeover(self) -> None:
        if self.adapters:
            _, _, allowed, _ = self.adapter_state(self.adapters[self.cursor])
            if allowed:
                self.begin_import(takeover=True)

    def begin_import(self, *, takeover: bool) -> None:
        if not self.adapters:
            return
        adapter = self.adapters[self.cursor]
        valid, _, allowed, _ = self.adapter_state(adapter)
        if not valid or (takeover and not allowed):
            return
        conflicts = [
            skill
            for skill in valid
            if (self.skill_layout.available / skill.name).exists()
            and content_hash(self.skill_layout.available / skill.name) != content_hash(skill.path)
        ]
        if conflicts:
            self.app.push_screen(
                ConflictScreen(len(conflicts)),
                lambda choice: self.perform_import(adapter, valid, takeover, choice),
            )
        else:
            self.perform_import(adapter, valid, takeover, "skip")

    def perform_import(
        self, adapter: Adapter, valid: list, takeover: bool, conflict: str | None
    ) -> None:
        if conflict is None:
            return
        try:
            imported = migrate(
                self.skill_layout,
                adapter,
                {skill.name for skill in valid},
                lambda *_: conflict,
                takeover=takeover,
            )
        except SkillctlError as error:
            self.notify(str(error), severity="error")
            return
        message = f"Imported {len(imported)} skill(s)"
        if takeover and adapter.path.is_symlink():
            message += " and took over adapter"
        self.notify(message, severity="information")
        self.refresh_view()
        self.post_message(self.Imported(imported))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "import-only":
            self.action_import_only()
        elif event.button.id == "takeover":
            self.action_takeover()


class SkillctlApp(App[None]):
    TITLE = "skillctl"
    SUB_TITLE = "Shared agent skills"
    BINDINGS: ClassVar = [
        ("up,k", "up", "Up"),
        ("down,j", "down", "Down"),
        Binding("space", "toggle_skill", "Toggle", show=False),
        ("1", "choose_tab", "Choose"),
        ("2", "import_tab", "Scan & Import"),
        Binding("i", "import_skills", "Import", show=False),
        Binding("t", "takeover", "Take over", show=False),
        ("enter", "primary", "Apply / Import"),
        ("escape,q", "quit", "Close"),
    ]
    CSS = """
    Screen {
        background: $background;
    }

    Header, Footer {
        background: $panel;
    }

    #workspace {
        width: 100%;
        max-width: 110;
        height: 1fr;
        margin: 0 2;
    }

    TabPane {
        padding: 0;
    }

    #choose-panel {
        height: 1fr;
    }

    #intro {
        height: 1;
        padding: 0 1;
    }

    #title {
        width: 1fr;
        text-style: bold;
        color: $text;
    }

    #summary {
        color: $text-muted;
        width: auto;
        height: 1;
        content-align: right middle;
    }

    #skills {
        height: 1fr;
        padding: 0 1;
        border: round $primary-background;
        background: $surface;
        overflow-x: hidden;
        overflow-y: auto;
        scrollbar-size-horizontal: 0;
        scrollbar-size-vertical: 1;
        scrollbar-color: $primary-background;
        scrollbar-color-hover: $primary;
    }

    #skills:focus {
        border: round $primary;
    }

    #detail {
        height: 2;
        padding: 0 1;
        border-left: thick $primary;
        background: $panel;
        color: $text-muted;
    }

    #actions {
        height: 3;
        align: right middle;
    }

    Button {
        width: auto;
        min-width: 14;
        height: 3;
        margin-left: 1;
    }
    """

    def __init__(
        self, layout: Layout, *, start_import: bool = False, initial_adapter: str | None = None
    ) -> None:
        super().__init__()
        self.layout = layout
        self.original = enabled_names(layout)
        self.desired = set(self.original)
        self.cursor = 0
        self.start_import = start_import
        self.initial_adapter = initial_adapter
        self.initial_tab = (
            "import-tab" if start_import or not available_skills(layout) else "choose-tab"
        )

    def compose(self) -> ComposeResult:
        yield Header(icon="◆")
        with TabbedContent(initial=self.initial_tab, id="workspace"):
            with TabPane("Choose", id="choose-tab"), Vertical(id="choose-panel"):
                with Horizontal(id="intro"):
                    yield Label("Choose skills", id="title")
                    yield Label("", id="summary")
                yield SkillList(id="skills", min_width=1, wrap=False, auto_scroll=False)
                yield Static("", id="detail", markup=False)
                with Horizontal(id="actions"):
                    yield Button("Apply changes", id="apply", variant="success", disabled=True)
                    yield Button("Close", id="close")
            with TabPane("Scan & Import", id="import-tab"):
                yield ImportPanel(self.layout, self.initial_adapter)
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_view()
        self.call_after_refresh(self.refresh_view)
        self.call_after_refresh(self.focus_active_tab)

    def on_resize(self, _event: events.Resize) -> None:
        self.call_after_refresh(self.refresh_view)

    @property
    def active_tab(self) -> str:
        return self.query_one("#workspace", TabbedContent).active

    def focus_active_tab(self) -> None:
        if self.active_tab == "import-tab":
            panel = self.query_one(ImportPanel)
            panel.refresh_view()
            self.query_one("#adapters", SkillList).focus()
        else:
            self.query_one("#skills", SkillList).focus()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == "import-tab" and self.desired != self.original:
            self.notify("Apply pending changes before importing", severity="warning")
            event.tabbed_content.active = "choose-tab"
            return
        self.call_after_refresh(self.focus_active_tab)

    def refresh_view(self) -> None:
        rows = available_skills(self.layout)
        if not rows:
            self.query_one("#skills", SkillList).update(
                Text.from_markup(
                    "\n[bold]No skills imported[/bold]\n[dim]Switch to Scan & Import to add skills.[/dim]"
                )
            )
            self.query_one("#detail", Static).update("Import from any configured adapter.")
            self.update_controls(0)
            return

        self.cursor = min(self.cursor, len(rows) - 1)
        skills = self.query_one("#skills", SkillList)
        content_width = max(24, skills.size.width - 5)
        name_width = max(8, content_width - 17)
        content = Text()
        content.append("   ")
        content.append("Skill".ljust(name_width), style="bold")
        content.append("State".rjust(14), style="bold")
        content.append("\n")
        content.append("   " + "─" * name_width + " " + "─" * 13, style="dim")
        content.append("\n")
        pending = self.desired.symmetric_difference(self.original)
        for index, skill in enumerate(rows):
            enabled = skill.name in self.desired
            changed = skill.name in pending
            pointer = "›" if index == self.cursor else " "
            name = skill.name
            if len(name) > name_width - 2:
                name = name[: name_width - 3] + "…"
            if skill.issue:
                name += " !"
            state = "Enabled" if enabled else "Off"
            if changed:
                state += " *"

            line = Text()
            line.append(f"{pointer} ", style="bold cyan" if index == self.cursor else "")
            line.append("●", style="green") if enabled else line.append("○", style="bright_black")
            line.append(" ")
            line.append(name.ljust(name_width), style="bold" if index == self.cursor else "")
            line.append(state.rjust(14), style="green" if enabled else "dim")
            if skill.issue:
                line.stylize("yellow", 4, 4 + len(name))
            if changed:
                line.stylize("yellow", len(line) - 1, len(line))
            if index == self.cursor:
                line.stylize("on #263445")
            content.append_text(line)
            if index < len(rows) - 1:
                content.append("\n")

        skills.update(content)
        self.call_after_refresh(self.scroll_skill_cursor_into_view)

        selected = rows[self.cursor]
        detail = Text()
        detail.append(selected.name, style="bold")
        detail.append("\n")
        detail.append(display_path(self.layout, selected.path), style="dim")
        if selected.issue:
            detail.append(f"\n{selected.issue}", style="yellow")
        self.query_one("#detail", Static).update(detail)
        self.update_controls(len(rows))

    def scroll_skill_cursor_into_view(self) -> None:
        skills = self.query_one("#skills", SkillList)
        skills.scroll_to_region(
            Region(0, self.cursor + 2, max(1, skills.size.width), 1),
            animate=False,
            immediate=True,
            x_axis=False,
        )

    def update_controls(self, total: int) -> None:
        pending = len(self.desired.symmetric_difference(self.original))
        enabled = len(self.desired)
        summary = Text()
        summary.append(f"{enabled} enabled", style="green")
        summary.append(f"  ·  {total} available", style="dim")
        if pending:
            summary.append(f"  ·  {pending} pending", style="yellow")
        self.query_one("#summary", Label).update(summary)

        apply_button = self.query_one("#apply", Button)
        apply_button.disabled = pending == 0
        apply_button.label = f"Apply changes ({pending})" if pending else "Apply changes"

    def action_toggle_skill(self) -> None:
        if self.active_tab != "choose-tab":
            return
        rows = available_skills(self.layout)
        if rows and rows[self.cursor].issue is None:
            self.desired.symmetric_difference_update({rows[self.cursor].name})
            self.refresh_view()

    def action_up(self) -> None:
        if self.active_tab == "import-tab":
            self.query_one(ImportPanel).action_up()
            return
        if self.cursor > 0:
            self.cursor -= 1
            self.refresh_view()

    def action_down(self) -> None:
        if self.active_tab == "import-tab":
            self.query_one(ImportPanel).action_down()
            return
        rows = available_skills(self.layout)
        if self.cursor < len(rows) - 1:
            self.cursor += 1
            self.refresh_view()

    def action_apply(self) -> None:
        if self.desired == self.original:
            return
        apply_enabled(self.layout, self.desired)
        self.original = set(self.desired)
        self.refresh_view()
        self.notify("Changes applied", severity="information")

    def action_choose_tab(self) -> None:
        self.query_one("#workspace", TabbedContent).active = "choose-tab"

    def action_import_tab(self) -> None:
        if self.desired != self.original:
            self.notify("Apply pending changes before importing", severity="warning")
            return
        self.query_one("#workspace", TabbedContent).active = "import-tab"

    def action_import_skills(self) -> None:
        if self.active_tab == "import-tab":
            self.query_one(ImportPanel).action_import_only()
        else:
            self.action_import_tab()

    def action_takeover(self) -> None:
        if self.active_tab == "import-tab":
            self.query_one(ImportPanel).action_takeover()

    def action_primary(self) -> None:
        if self.active_tab == "import-tab":
            self.query_one(ImportPanel).action_import_only()
        else:
            self.action_apply()

    def on_import_panel_imported(self, event: ImportPanel.Imported) -> None:
        self.original = enabled_names(self.layout)
        self.desired = set(self.original)
        self.refresh_view()
        if event.names:
            self.notify(f"Imported {len(event.names)} skill(s)", severity="information")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "apply":
            self.action_apply()
        elif event.button.id == "close":
            self.exit()
