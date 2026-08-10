from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

from .core import Layout, SkillctlError, available_skills, doctor, migrate, restore, scan_adapter
from .tui import SkillctlApp


def console() -> Console:
    # Construct on demand so pytest capture and redirected output keep working.
    return Console(highlight=False)


def layout_from_args(args: argparse.Namespace) -> Layout:
    return Layout(Path(args.home).expanduser()) if args.home else Layout.default()


def display_path(layout: Layout, path: Path) -> str:
    try:
        relative = path.relative_to(layout.home)
    except ValueError:
        return str(path)
    return "~" if not relative.parts else f"~/{relative}"


def adapter_heading(layout: Layout, adapter) -> None:
    line = Text()
    line.append(f"[{adapter.name}]", style="bold cyan")
    line.append(f"  {display_path(layout, adapter.path)}", style="dim")
    console().print(line)


def print_result(message: str, *, kind: str = "success") -> None:
    icon, style = {
        "success": ("✓", "green"),
        "warning": ("!", "yellow"),
        "error": ("✗", "bold red"),
        "info": ("·", "cyan"),
    }[kind]
    line = Text()
    line.append(f"{icon} ", style=style)
    line.append(message)
    console().print(line)


def pick_adapter(layout: Layout, name: str):
    for adapter in layout.adapters():
        if adapter.name == name:
            return adapter
    raise SkillctlError(f"unknown adapter: {name}")


def print_overview(layout: Layout) -> None:
    skills = available_skills(layout)
    enabled = [x for x in skills if x.enabled]
    console().print(
        f"[bold]Skills[/bold]  [green]{len(enabled)} enabled[/green]"
        f" [dim]/ {len(skills)} available[/dim]"
    )
    for skill in skills:
        line = Text("  ")
        line.append("● ", style="green") if skill.enabled else line.append("○ ", style="dim")
        line.append(skill.name, style=None if skill.issue is None else "yellow")
        if skill.issue:
            line.append(f"  {skill.issue}", style="dim yellow")
        console().print(line)
    if not skills:
        console().print("  · No imported skills", style="dim")
    console().print("\n[bold]Adapters[/bold]")
    for adapter in layout.adapters():
        line = Text("  ")
        if adapter.path.is_symlink():
            icon, state, style = "● ", "taken over", "green"
        elif not adapter.path.exists():
            icon, state, style = "! ", "missing", "yellow"
        else:
            icon, state, style = "○ ", "local", "dim"
        line.append(icon, style=style)
        line.append(adapter.name)
        line.append(f"  {state}", style=style)
        console().print(line)


def cmd_check(layout: Layout) -> int:
    print_overview(layout)
    issues = doctor(layout)
    console().print("\n[bold]Health[/bold]")
    if issues:
        for issue in issues:
            print_result(issue, kind="warning")
    else:
        print_result("No issues found")
    return 1 if issues else 0


def cmd_import(layout: Layout, args: argparse.Namespace) -> int:
    adapter = pick_adapter(layout, args.adapter)
    return import_adapter(layout, adapter, args.skills)


def import_adapter(
    layout: Layout, adapter, requested_skills: list[str], show_header: bool = True
) -> int:
    report = scan_adapter(layout, adapter)
    found = [item for item in report if item.issue is None]
    issues = [item for item in report if item.issue is not None]
    names = set(requested_skills or [x.name for x in found])
    if show_header:
        adapter_heading(layout, adapter)
    if not names:
        console().print("  Skipped: no importable skills", style="dim")
        return 0
    console().print("  Skills  " + (", ".join(sorted(names)) if names else "none"))
    if issues:
        console().print(
            "  Ignored  " + ", ".join(f"{item.name} ({item.issue})" for item in issues),
            style="yellow",
        )

    imported = migrate(layout, adapter, names, lambda *_: "skip")
    if imported:
        print_result(f"Imported {len(imported)}: {', '.join(imported)}")
    else:
        print_result("No skills imported", kind="info")
    return 0


def cmd_import_all(layout: Layout) -> int:
    console().print("[bold]Import review[/bold]")
    for index, adapter in enumerate(layout.adapters()):
        if index:
            console().print()
        adapter_heading(layout, adapter)
        if not adapter.path.exists() and not adapter.path.is_symlink():
            console().print("  Skipped: skill root does not exist", style="dim")
            continue
        report = scan_adapter(layout, adapter)
        skills = [item.name for item in report if not item.issue]
        if not skills:
            console().print("  Skipped: no importable skills", style="dim")
            continue
        import_adapter(layout, adapter, skills, show_header=False)
    return 0


def is_interactive() -> bool:
    return sys.stdin.isatty() and console().is_terminal


def cmd_manage(layout: Layout) -> int:
    if not is_interactive():
        return cmd_check(layout)
    SkillctlApp(layout).run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillctl",
        description="Manage shared agent skills. Run without a command for the interactive UI.",
    )
    parser.add_argument(
        "--home", help="HOME for testing or isolation; defaults to the current user home"
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    import_parser = sub.add_parser("import", help="discover and import skills from adapters")
    import_parser.add_argument(
        "adapter", nargs="?", help="adapter name; omit to review every adapter"
    )
    import_parser.add_argument("skills", nargs="*")
    import_parser.add_argument("-y", "--yes", action="store_true")
    sub.add_parser("check", help="show status and run diagnostics")
    restore_parser = sub.add_parser("restore", help="restore an adapter taken over by skillctl")
    restore_parser.add_argument("adapter")
    restore_parser.add_argument("--backup", help="backup timestamp; defaults to the latest backup")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(arguments)
    layout = layout_from_args(args)
    try:
        layout.initialize()
        if args.command is None:
            return cmd_manage(layout)
        if args.command == "import":
            if is_interactive() and not args.yes:
                SkillctlApp(layout, start_import=True, initial_adapter=args.adapter).run()
                return 0
            if not args.yes:
                raise SkillctlError("non-interactive import requires --yes")
            return cmd_import(layout, args) if args.adapter else cmd_import_all(layout)
        if args.command == "check":
            return cmd_check(layout)
        if args.command == "restore":
            restored = restore(layout, pick_adapter(layout, args.adapter), args.backup)
            print_result(f"Restored from {display_path(layout, restored)}")
        return 0
    except SkillctlError as error:
        print_result(f"Error: {error}", kind="error")
        return 2
    except (EOFError, KeyboardInterrupt):
        console().print()
        print_result("Cancelled", kind="info")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
