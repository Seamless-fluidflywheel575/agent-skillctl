from skillctl.cli import main


def test_cli_without_command_initializes_and_checks_when_not_interactive(tmp_path, capsys):
    home = tmp_path / "home"
    assert main(["--home", str(home)]) == 0
    output = capsys.readouterr().out
    assert "Skills" in output
    assert "Health" in output
    assert "No issues found" in output
    assert (home / ".agents/config.toml").exists()


def test_cli_interactive_run_opens_tui(tmp_path, monkeypatch):
    home = tmp_path / "home"
    opened = []
    monkeypatch.setattr("skillctl.cli.is_interactive", lambda: True)
    monkeypatch.setattr("skillctl.cli.SkillctlApp.run", lambda app: opened.append(app))

    assert main(["--home", str(home)]) == 0
    assert len(opened) == 1
    assert not opened[0].start_import


def test_cli_check_combines_status_and_doctor(tmp_path, capsys):
    home = str(tmp_path / "home")
    assert main(["--home", home, "check"]) == 0
    output = capsys.readouterr().out
    assert "0 enabled / 0 available" in output
    assert "openclaw  missing" in output
    assert "No issues found" in output
    assert "\x1b[" not in output


def test_noninteractive_import_without_adapter_uses_safe_mode(tmp_path, capsys):
    home = tmp_path / "home"
    assert main(["--home", str(home), "check"]) == 0
    skill = home / ".agents" / "skills" / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# alpha\n")
    assert main(["--home", str(home), "import", "-y"]) == 0
    output = capsys.readouterr().out
    assert "[agents]" in output
    assert "[openclaw]" in output
    assert "Skipped: skill root does not exist" in output
    assert "[codex]" in output
    assert output.count("Skipped: skill root does not exist") == 3
    assert (home / ".agents" / "skills" / "alpha").is_symlink()


def test_interactive_import_command_opens_tui_import_screen(tmp_path, monkeypatch):
    home = tmp_path / "home"
    opened = []
    monkeypatch.setattr("skillctl.cli.is_interactive", lambda: True)
    monkeypatch.setattr("skillctl.cli.SkillctlApp.run", lambda app: opened.append(app))

    assert main(["--home", str(home), "import", "demo"]) == 0
    assert len(opened) == 1
    assert opened[0].start_import
    assert opened[0].initial_adapter == "demo"


def test_noninteractive_import_requires_yes(tmp_path, capsys):
    assert main(["--home", str(tmp_path / "home"), "import"]) == 2
    assert "requires --yes" in capsys.readouterr().out


def test_import_only_skips_invalid_adapter_content(tmp_path, capsys):
    home = tmp_path / "home"
    assert main(["--home", str(home), "check"]) == 0
    config = home / ".agents/config.toml"
    config.write_text('[[adapters]]\nname = "demo"\npath = "~/.demo/skills"\n')
    root = home / ".demo/skills"
    skill = root / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# alpha\n")
    (root / ".system").mkdir()
    (root / "runtime").mkdir()
    assert main(["--home", str(home), "import", "demo", "-y"]) == 0
    output = capsys.readouterr().out
    assert "Ignored" in output
    assert (home / ".agents/skills-available/alpha").is_dir()
    assert root.is_dir() and not root.is_symlink()
