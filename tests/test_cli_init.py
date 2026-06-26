"""Snapshot tests for `gaiaagent init` project scaffolding.

Verifies that `_cmd_init` produces the expected agent.py, README.md and
requirements.txt with the project name substituted in, and that the
generated agent.py is importable Python.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from gaiaagent.cli import _AGENT_TEMPLATE, _README_TEMPLATE, _cmd_init


def _run_init(tmp_path: Path, name: str) -> Path:
    """Invoke _cmd_init the same way the CLI would, returning the project dir."""
    args = argparse.Namespace(name=name, quiet=False)
    monkey_cwd = tmp_path / name
    # _cmd_init uses Path(args.name) relative to CWD; chdir into tmp_path.
    import os

    orig = Path.cwd()
    os.chdir(tmp_path)
    try:
        rc = _cmd_init(args)
        assert rc == 0
    finally:
        os.chdir(orig)
    assert monkey_cwd.exists()
    return monkey_cwd


class TestInitScaffold:
    """Snapshot assertions on the generated project files."""

    def test_creates_all_files(self, tmp_path: Path):
        project = _run_init(tmp_path, "myagent")
        assert (project / "agent.py").is_file()
        assert (project / "README.md").is_file()
        assert (project / "requirements.txt").is_file()

    def test_agent_py_matches_template(self, tmp_path: Path):
        project = _run_init(tmp_path, "myagent")
        expected = _AGENT_TEMPLATE.replace("__PROJECT__", "myagent")
        assert (project / "agent.py").read_text(encoding="utf-8") == expected

    def test_readme_matches_template(self, tmp_path: Path):
        project = _run_init(tmp_path, "myagent")
        expected = _README_TEMPLATE.replace("__PROJECT__", "myagent")
        assert (project / "README.md").read_text(encoding="utf-8") == expected

    def test_requirements_content(self, tmp_path: Path):
        project = _run_init(tmp_path, "myagent")
        assert (project / "requirements.txt").read_text(encoding="utf-8") == "gaiaagent[http]\n"

    def test_project_name_substituted(self, tmp_path: Path):
        project = _run_init(tmp_path, "deep-researcher")
        agent_src = (project / "agent.py").read_text(encoding="utf-8")
        assert "aurc:deep-researcher/myagent:v1.0" in agent_src
        assert "__PROJECT__" not in agent_src

    def test_returns_error_if_dir_exists(self, tmp_path: Path):
        (tmp_path / "exists").mkdir()
        args = argparse.Namespace(name="exists", quiet=False)
        orig = Path.cwd()
        import os

        os.chdir(tmp_path)
        try:
            rc = _cmd_init(args)
        finally:
            os.chdir(orig)
        assert rc == 1
        # existing dir should be left untouched (no agent.py written into it)
        assert not (tmp_path / "exists" / "agent.py").exists()

    def test_generated_agent_py_is_importable(self, tmp_path: Path):
        """The scaffolded agent.py should be valid, importable Python."""
        project = _run_init(tmp_path, "myagent")
        check_cmd = (
            "import ast; ast.parse(open('agent.py',encoding='utf-8').read())"
        )
        result = subprocess.run(
            [sys.executable, "-c", check_cmd],
            cwd=str(project),
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr.decode()

    def test_generated_agent_greet_runs(self, tmp_path: Path):
        """End-to-end: running the generated agent should print a greeting."""
        project = _run_init(tmp_path, "myagent")
        result = subprocess.run(
            [sys.executable, "agent.py"],
            cwd=str(project),
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
        out = result.stdout.decode("utf-8", "replace")
        assert "Hello, World" in out
