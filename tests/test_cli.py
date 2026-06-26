"""Tests for CLI tool — aurc command-line interface.
CLI 工具测试 — aurc 命令行界面
"""

import json
import os
import sys
import tempfile

import pytest


class TestCLIVersion:
    """Tests for the 'version' subcommand."""

    def test_version_command(self, capsys):
        """aurc version should print version info."""
        from gaiaagent.cli import main
        sys.argv = ["aurc", "version"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "0.1.0" in captured.out

    def test_version_quiet(self, capsys):
        """aurc version --quiet should print just the version."""
        from gaiaagent.cli import main
        sys.argv = ["aurc", "version", "--quiet"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "0.1.0" in captured.out


class TestCLIInfo:
    """Tests for the 'info' subcommand."""

    def test_info_command(self, capsys):
        """aurc info should print protocol info."""
        from gaiaagent.cli import main
        sys.argv = ["aurc", "info"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "AURC" in captured.out or "aurc" in captured.out.lower()

    def test_info_quiet(self, capsys):
        """aurc info --quiet should print JSON."""
        from gaiaagent.cli import main
        sys.argv = ["aurc", "info", "--quiet"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, dict)


class TestCLIBridgeTest:
    """Tests for the 'bridge test' subcommand."""

    def test_bridge_test_mcp(self, capsys):
        """aurc bridge test --protocol mcp should succeed."""
        from gaiaagent.cli import main
        sys.argv = ["aurc", "bridge", "test", "--protocol", "mcp"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "mcp" in captured.out.lower()

    def test_bridge_test_a2a(self, capsys):
        """aurc bridge test --protocol a2a should succeed."""
        from gaiaagent.cli import main
        sys.argv = ["aurc", "bridge", "test", "--protocol", "a2a"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "a2a" in captured.out.lower()

    def test_bridge_test_acp(self, capsys):
        """aurc bridge test --protocol acp should run."""
        from gaiaagent.cli import main
        sys.argv = ["aurc", "bridge", "test", "--protocol", "acp"]
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "acp" in captured.out.lower()


class TestCLIValidate:
    """Tests for the 'validate' subcommand."""

    def test_validate_valid_descriptor(self, capsys):
        """Valid Agent Descriptor JSON should pass validation."""
        from gaiaagent.cli import main
        descriptor = {
            "aurc_id": "aurc:test/agent:v1.0",
            "display_name": "Test Agent",
            "description": "A test agent",
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(descriptor, f)
            f.flush()
            tmpfile = f.name

        try:
            sys.argv = ["aurc", "validate", tmpfile]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
            captured = capsys.readouterr()
            assert "valid" in captured.out.lower() or "ok" in captured.out.lower()
        finally:
            os.unlink(tmpfile)

    def test_validate_missing_file(self, capsys):
        """Non-existent file should show error."""
        from gaiaagent.cli import main
        sys.argv = ["aurc", "validate", "/nonexistent/path.json"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code != 0


class TestCLIRegistryExport:
    """Tests for the 'registry export' subcommand."""

    def test_registry_export(self, capsys):
        """aurc registry export should output JSON."""
        from gaiaagent.cli import main
        sys.argv = ["aurc", "registry", "export"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        # Should contain valid JSON somewhere in output
        assert "[" in captured.out or "{" in captured.out
